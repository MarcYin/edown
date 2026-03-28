from __future__ import annotations

import math
import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from os import terminal_size
from typing import Callable, Deque, Optional, Protocol, Sequence, TextIO

from .models import DownloadResult

# Chunk grid characters
_CHUNK_DONE = "■"
_CHUNK_PENDING = "□"
_CHUNK_FAILED = "▣"
_CHUNK_PARTIAL = "▨"
_CHUNK_INACTIVE = "·"

# Progress bar characters
_BAR_FILL = "█"
_BAR_EMPTY = "░"

# Status icons
_ICON_DONE = "✓"
_ICON_ACTIVE = "↓"
_ICON_FAILED = "✗"
_ICON_SKIPPED = "-"
_ICON_QUEUED = "·"

# ANSI escape codes
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_CYAN = "\x1b[36m"

_MAX_GRID_PREVIEW_ROWS = 3
_MAX_GRID_PREVIEW_COLS = 16
_SPEED_WINDOW = 30


class DownloadProgressReporter(Protocol):
    def on_search_result(self, image_ids: Sequence[str]) -> None: ...

    def on_prepare_result(self, result: DownloadResult) -> None: ...

    def on_job_prepared(self, image_id: str, chunk_count: int) -> None: ...

    def on_chunk_complete(self, image_id: str) -> None: ...

    def on_job_failed(self, image_id: str, error: str) -> None: ...

    def on_job_finished(self, result: DownloadResult) -> None: ...

    def close(self) -> None: ...


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m"


def _progress_bar(fraction: float, width: int) -> str:
    width = max(1, width)
    fraction = max(0.0, min(1.0, fraction))
    filled = int(fraction * width)
    return _BAR_FILL * filled + _BAR_EMPTY * (width - filled)


@dataclass
class _TileState:
    image_id: str
    status: str = "queued"
    chunk_total: int = 0
    chunk_done: int = 0
    chunk_rows: int = 0
    chunk_cols: int = 0
    chunk_cells: list[str] = field(default_factory=list)
    error: Optional[str] = None
    updated_at: float = 0.0
    final: bool = False
    track_chunks: bool = False


class TerminalDownloadProgress:
    def __init__(
        self,
        *,
        stream: TextIO,
        enabled: Optional[bool] = None,
        terminal_width: Optional[int] = None,
        min_render_interval: float = 0.05,
        max_visible_tiles: int = 4,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._stream = stream
        self._enabled = bool(stream.isatty()) if enabled is None else enabled
        self._terminal_width = terminal_width
        self._min_render_interval = min_render_interval
        self._max_visible_tiles = max(1, max_visible_tiles)
        self._clock = clock or time.monotonic
        self._tiles: dict[str, _TileState] = {}
        self._tile_order: list[str] = []
        self._rendered_line_count = 0
        self._last_rendered_at = 0.0
        self._render_pending = False
        self._cursor_hidden = False
        self._closed = False
        self._start_time: Optional[float] = None
        self._chunk_timestamps: Deque[float] = deque(maxlen=_SPEED_WINDOW)

    # ── Event handlers ──────────────────────────────────────────────────

    def on_search_result(self, image_ids: Sequence[str]) -> None:
        now = self._clock()
        if self._start_time is None:
            self._start_time = now
        self._tile_order = list(image_ids)
        for image_id in image_ids:
            tile = self._tiles.setdefault(image_id, _TileState(image_id=image_id))
            tile.updated_at = now
        self._request_render(force=True)

    def on_prepare_result(self, result: DownloadResult) -> None:
        tile = self._ensure_tile(result.image_id)
        tile.status = result.status
        tile.chunk_total = result.chunk_count
        tile.chunk_done = result.chunk_count if result.status == "downloaded" else 0
        tile.chunk_rows = 0
        tile.chunk_cols = 0
        tile.chunk_cells = []
        tile.track_chunks = False
        tile.error = result.error
        tile.final = True
        tile.updated_at = self._clock()
        self._request_render(force=True)

    def on_job_prepared(self, image_id: str, chunk_count: int) -> None:
        tile = self._ensure_tile(image_id)
        tile.status = "downloading"
        tile.chunk_total = chunk_count
        tile.chunk_done = 0
        tile.track_chunks = chunk_count > 0
        tile.error = None
        tile.final = False
        tile.updated_at = self._clock()
        self._request_render(force=True)

    def on_job_chunk_grid(
        self,
        image_id: str,
        chunk_rows: int,
        chunk_cols: int,
        active_cells: Sequence[tuple[int, int]],
    ) -> None:
        tile = self._ensure_tile(image_id)
        tile.chunk_rows = max(0, chunk_rows)
        tile.chunk_cols = max(0, chunk_cols)
        tile.chunk_cells = ["inactive"] * (tile.chunk_rows * tile.chunk_cols)
        for row_index, col_index in active_cells:
            if 0 <= row_index < tile.chunk_rows and 0 <= col_index < tile.chunk_cols:
                tile.chunk_cells[(row_index * tile.chunk_cols) + col_index] = "pending"
        tile.updated_at = self._clock()
        self._request_render(force=True)

    def on_chunk_complete(self, image_id: str) -> None:
        tile = self._ensure_tile(image_id)
        if tile.final and tile.status == "failed":
            return
        tile.status = "downloading"
        tile.chunk_done = min(tile.chunk_total, tile.chunk_done + 1)
        tile.track_chunks = tile.chunk_total > 0
        tile.updated_at = self._clock()
        self._chunk_timestamps.append(tile.updated_at)
        self._request_render(force=False)

    def on_chunk_cell_complete(self, image_id: str, row_index: int, col_index: int) -> None:
        tile = self._ensure_tile(image_id)
        if tile.chunk_cols <= 0 or not tile.chunk_cells:
            return
        if not (0 <= row_index < tile.chunk_rows and 0 <= col_index < tile.chunk_cols):
            return
        index = (row_index * tile.chunk_cols) + col_index
        if tile.chunk_cells[index] == "pending":
            tile.chunk_cells[index] = "done"
        tile.updated_at = self._clock()

    def on_job_failed(self, image_id: str, error: str) -> None:
        tile = self._ensure_tile(image_id)
        tile.status = "failed"
        tile.error = error
        tile.final = True
        tile.track_chunks = tile.chunk_total > 0
        tile.chunk_cells = [
            "failed" if state == "pending" else state for state in tile.chunk_cells
        ]
        tile.updated_at = self._clock()
        self._request_render(force=True)

    def on_job_finished(self, result: DownloadResult) -> None:
        tile = self._ensure_tile(result.image_id)
        tile.status = result.status
        tile.error = result.error
        tile.final = True
        tile.updated_at = self._clock()
        if result.status == "downloaded":
            tile.chunk_total = max(tile.chunk_total, result.chunk_count)
            tile.chunk_done = tile.chunk_total
            tile.track_chunks = tile.chunk_total > 0
            tile.chunk_cells = [
                "done" if state == "pending" else state for state in tile.chunk_cells
            ]
        elif result.status == "failed":
            tile.chunk_total = max(tile.chunk_total, result.chunk_count)
            tile.track_chunks = tile.chunk_total > 0
            tile.chunk_cells = [
                "failed" if state == "pending" else state for state in tile.chunk_cells
            ]
        else:
            tile.chunk_total = result.chunk_count
            tile.track_chunks = False
            tile.chunk_rows = 0
            tile.chunk_cols = 0
            tile.chunk_cells = []
        self._request_render(force=True)

    # ── Rendering ───────────────────────────────────────────────────────

    def render_lines(self, width: Optional[int] = None) -> list[str]:
        if not self._tile_order:
            return []

        w = max(40, width or self._terminal_width or self._terminal_size().columns)
        tiles = [self._tiles[iid] for iid in self._tile_order if iid in self._tiles]

        finished = sum(1 for t in tiles if t.final)
        total_chunks = sum(t.chunk_total for t in tiles if t.track_chunks)
        done_chunks = sum(t.chunk_done for t in tiles if t.track_chunks)

        lines: list[str] = []

        # ── Header ──
        lines.append(self._header_line(w))

        # Overall progress bar
        frac = done_chunks / total_chunks if total_chunks > 0 else 0.0
        pct = int(frac * 100)
        bar_w = max(10, min(40, w - 46))
        bar = _progress_bar(frac, bar_w)
        lines.append(self._trim(
            f"  {bar} {pct:>3}%  {finished}/{len(tiles)} tiles"
            f"  {done_chunks}/{total_chunks} chunks",
            w,
        ))

        # Timing line
        elapsed = self._elapsed()
        speed = self._chunks_per_min()
        eta = self._estimate_eta(total_chunks, done_chunks, speed)
        parts = [f"elapsed {_format_duration(elapsed)}"]
        if speed > 0:
            parts.append(f"{speed:.1f} chunks/min")
        if eta is not None and eta > 0:
            parts.append(f"ETA ~{_format_duration(eta)}")
        lines.append(self._trim(f"  {' · '.join(parts)}", w))

        # Blank separator
        lines.append("")

        # Tile lines
        visible = self._visible_tiles(tiles)
        for tile in visible:
            lines.extend(self._render_tile(tile, w))

        hidden = len(tiles) - len(visible)
        if hidden > 0:
            lines.append(self._trim(f"  … {hidden} more tiles queued", w))

        return lines

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._enabled:
            return
        if self._render_pending:
            self._render()
        if self._cursor_hidden:
            self._stream.write("\x1b[?25h")
        if self._rendered_line_count:
            self._stream.write("\n")
        self._stream.flush()

    # ── Private helpers ─────────────────────────────────────────────────

    def _header_line(self, width: int) -> str:
        label = "━━ edown "
        return label + "━" * max(0, width - len(label))

    def _elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        return max(0.0, self._clock() - self._start_time)

    def _chunks_per_min(self) -> float:
        if len(self._chunk_timestamps) < 2:
            return 0.0
        span = self._chunk_timestamps[-1] - self._chunk_timestamps[0]
        if span < 1.0:
            return 0.0
        return (len(self._chunk_timestamps) - 1) / span * 60.0

    def _estimate_eta(self, total: int, done: int, speed: float) -> Optional[float]:
        remaining = total - done
        if remaining <= 0 or speed <= 0:
            return None
        return (remaining / speed) * 60.0

    def _ensure_tile(self, image_id: str) -> _TileState:
        tile = self._tiles.get(image_id)
        if tile is None:
            tile = _TileState(image_id=image_id, updated_at=self._clock())
            self._tiles[image_id] = tile
            self._tile_order.append(image_id)
        return tile

    def _request_render(self, *, force: bool) -> None:
        if not self._enabled or self._closed:
            return
        now = self._clock()
        if force or (now - self._last_rendered_at) >= self._min_render_interval:
            self._render()
            return
        self._render_pending = True

    def _render(self) -> None:
        lines = self.render_lines()
        if not lines:
            return
        if not self._cursor_hidden:
            self._stream.write("\x1b[?25l")
            self._cursor_hidden = True

        colored = [self._colorize(line) for line in lines]
        output_lines = list(colored)
        if self._rendered_line_count > len(output_lines):
            output_lines.extend([""] * (self._rendered_line_count - len(output_lines)))

        if self._rendered_line_count:
            self._stream.write("\r")
            if self._rendered_line_count > 1:
                self._stream.write(f"\x1b[{self._rendered_line_count - 1}A")

        for index, line in enumerate(output_lines):
            self._stream.write("\x1b[2K")
            self._stream.write(line)
            if index < len(output_lines) - 1:
                self._stream.write("\n")

        self._stream.flush()
        self._render_pending = False
        self._rendered_line_count = len(output_lines)
        self._last_rendered_at = self._clock()

    def _colorize(self, line: str) -> str:
        if not line:
            return line
        if line.startswith("━"):
            return f"{_DIM}{line}{_RESET}"
        if line.strip().startswith("elapsed"):
            return f"{_DIM}{line}{_RESET}"
        if _BAR_FILL in line or _BAR_EMPTY in line:
            result: list[str] = []
            for ch in line:
                if ch == _BAR_FILL:
                    result.append(f"{_GREEN}{ch}{_RESET}")
                elif ch == _BAR_EMPTY:
                    result.append(f"{_DIM}{ch}{_RESET}")
                else:
                    result.append(ch)
            return "".join(result)
        if f"  {_ICON_FAILED} " in line:
            return f"{_RED}{line}{_RESET}"
        if f"  {_ICON_ACTIVE} " in line:
            return f"{_YELLOW}{line}{_RESET}"
        if f"  {_ICON_DONE} " in line:
            return f"{_GREEN}{line}{_RESET}"
        if f"  {_ICON_SKIPPED} " in line:
            return f"{_DIM}{line}{_RESET}"
        if line.strip().startswith("error:"):
            return f"{_RED}{line}{_RESET}"
        stripped = line.strip()
        if stripped and all(
            ch in (_CHUNK_DONE, _CHUNK_PENDING, _CHUNK_FAILED, _CHUNK_PARTIAL,
                   _CHUNK_INACTIVE, " ", "/")
            for ch in stripped
        ):
            result = []
            for ch in line:
                if ch == _CHUNK_DONE:
                    result.append(f"{_GREEN}{ch}{_RESET}")
                elif ch == _CHUNK_FAILED:
                    result.append(f"{_RED}{ch}{_RESET}")
                elif ch == _CHUNK_PARTIAL:
                    result.append(f"{_YELLOW}{ch}{_RESET}")
                elif ch in (_CHUNK_PENDING, _CHUNK_INACTIVE):
                    result.append(f"{_DIM}{ch}{_RESET}")
                else:
                    result.append(ch)
            return "".join(result)
        if line.strip().startswith("…"):
            return f"{_DIM}{line}{_RESET}"
        return line

    def _tile_icon(self, tile: _TileState) -> str:
        if tile.status == "downloaded":
            return _ICON_DONE
        if tile.status == "downloading":
            return _ICON_ACTIVE
        if tile.status == "failed":
            return _ICON_FAILED
        if tile.status.startswith("skipped"):
            return _ICON_SKIPPED
        return _ICON_QUEUED

    def _visible_tiles(self, tiles: list[_TileState]) -> list[_TileState]:
        active_tiles = [
            tile for tile in tiles if tile.status == "downloading" and not tile.final
        ]
        active_image_ids = {tile.image_id for tile in active_tiles}
        finished_tiles = [
            tile
            for tile in tiles
            if tile.final
            and tile.status != "queued"
            and tile.image_id not in active_image_ids
        ]
        queued_tiles = [
            tile
            for tile in tiles
            if tile.status == "queued" and tile.image_id not in active_image_ids
        ]
        non_active_tiles = finished_tiles + queued_tiles
        extra_slots = max(0, self._max_visible_tiles - len(active_tiles))
        return active_tiles + non_active_tiles[:extra_slots]

    def _render_tile(self, tile: _TileState, width: int) -> list[str]:
        icon = self._tile_icon(tile)
        label_w = max(12, min(24, width // 4))
        label = self._short_label(tile.image_id, label_w)
        status = self._status_text(tile)

        if tile.chunk_total > 0 and tile.track_chunks:
            pct = int((tile.chunk_done * 100) / tile.chunk_total)
            bar_w = max(6, min(20, width - label_w - 32))
            frac = tile.chunk_done / tile.chunk_total
            bar = _progress_bar(frac, bar_w)
            count = f"{tile.chunk_done}/{tile.chunk_total}"
            line = f"  {icon} {label:<{label_w}}  {status:<12} {bar} {count:>7} {pct:>3}%"
        else:
            line = f"  {icon} {label:<{label_w}}  {status}"

        if tile.chunk_rows > 0 and tile.chunk_cols > 0 and tile.chunk_cells:
            line = f"{line}  {tile.chunk_rows}x{tile.chunk_cols}"

        lines = [self._trim(line, width)]

        # 2D grid preview on a separate indented line
        if tile.chunk_rows > 0 and tile.chunk_cols > 0 and tile.chunk_cells:
            preview_rows = self._grid_chunk_rows(tile, width)
            if preview_rows:
                preview = " / ".join(preview_rows)
                lines.append(self._trim(f"    {preview}", width))

        if tile.error and tile.status == "failed":
            lines.append(self._trim(f"    error: {tile.error}", width))

        return lines

    # ── Chunk grid visualization ────────────────────────────────────────

    def _grid_chunk_rows(self, tile: _TileState, row_width: int) -> list[str]:
        if tile.chunk_rows <= 0 or tile.chunk_cols <= 0 or not tile.chunk_cells:
            return []

        max_cols = max(4, min(_MAX_GRID_PREVIEW_COLS, max(4, row_width // 3)))
        scale = max(
            tile.chunk_cols / max_cols,
            tile.chunk_rows / _MAX_GRID_PREVIEW_ROWS,
            1.0,
        )
        render_cols = max(1, min(tile.chunk_cols, math.ceil(tile.chunk_cols / scale)))
        render_rows = max(
            1, min(tile.chunk_rows, math.ceil(tile.chunk_rows / scale), _MAX_GRID_PREVIEW_ROWS)
        )

        if render_cols == tile.chunk_cols and render_rows == tile.chunk_rows:
            return [
                "".join(
                    self._chunk_symbol(tile.chunk_cells[(row * tile.chunk_cols) + col])
                    for col in range(tile.chunk_cols)
                )
                for row in range(tile.chunk_rows)
            ]

        row_lines: list[str] = []
        for render_row in range(render_rows):
            source_row0 = math.floor((render_row * tile.chunk_rows) / render_rows)
            source_row1 = math.floor(((render_row + 1) * tile.chunk_rows) / render_rows)
            line_cells: list[str] = []
            for render_col in range(render_cols):
                source_col0 = math.floor((render_col * tile.chunk_cols) / render_cols)
                source_col1 = math.floor(((render_col + 1) * tile.chunk_cols) / render_cols)
                states: list[str] = []
                for row_index in range(source_row0, max(source_row0 + 1, source_row1)):
                    for col_index in range(source_col0, max(source_col0 + 1, source_col1)):
                        if row_index >= tile.chunk_rows or col_index >= tile.chunk_cols:
                            continue
                        states.append(tile.chunk_cells[(row_index * tile.chunk_cols) + col_index])
                line_cells.append(self._aggregate_chunk_symbol(states))
            row_lines.append("".join(line_cells))
        return row_lines

    def _aggregate_chunk_symbol(self, states: Sequence[str]) -> str:
        active_states = [state for state in states if state != "inactive"]
        if not active_states:
            return _CHUNK_INACTIVE
        if any(state == "failed" for state in active_states):
            return _CHUNK_FAILED
        if all(state == "done" for state in active_states):
            return _CHUNK_DONE
        if all(state == "pending" for state in active_states):
            return _CHUNK_PENDING
        return _CHUNK_PARTIAL

    def _chunk_symbol(self, state: str) -> str:
        mapping = {
            "done": _CHUNK_DONE,
            "pending": _CHUNK_PENDING,
            "failed": _CHUNK_FAILED,
            "inactive": _CHUNK_INACTIVE,
        }
        return mapping.get(state, _CHUNK_PENDING)

    def _status_text(self, tile: _TileState) -> str:
        labels = {
            "queued": "queued",
            "downloading": "downloading",
            "downloaded": "done",
            "failed": "failed",
            "skipped_existing": "cached",
            "skipped_outside_aoi": "outside AOI",
            "skipped_missing_bands": "missing bands",
        }
        if tile.status in labels:
            return labels[tile.status]
        if tile.status.startswith("skipped_"):
            return tile.status.replace("skipped_", "skip ").replace("_", " ")
        return tile.status.replace("_", " ")

    def _short_label(self, image_id: str, max_length: int) -> str:
        label = image_id.rsplit("/", 1)[-1]
        if len(label) <= max_length:
            return label
        if max_length <= 3:
            return label[:max_length]
        return f"{label[: max_length - 3]}..."

    def _trim(self, line: str, width: int) -> str:
        if len(line) <= width:
            return line
        if width <= 3:
            return line[:width]
        return f"{line[: width - 3]}..."

    def _terminal_size(self) -> terminal_size:
        return shutil.get_terminal_size(fallback=(100, 20))
