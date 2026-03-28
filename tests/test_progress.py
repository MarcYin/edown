import io

from edown import DownloadResult
from edown.progress import _BAR_EMPTY, _BAR_FILL, TerminalDownloadProgress


def _header_line_count() -> int:
    """Number of fixed header lines: header, progress bar, timing, blank."""
    return 4


def test_terminal_progress_renders_overall_bar_and_tile_bars() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
        max_visible_tiles=3,
    )

    progress.on_search_result(("COLLECTION/IMG_1", "COLLECTION/IMG_2"))
    progress.on_job_prepared("COLLECTION/IMG_1", 5)
    progress.on_job_prepared("COLLECTION/IMG_2", 3)
    progress.on_chunk_complete("COLLECTION/IMG_1")
    progress.on_chunk_complete("COLLECTION/IMG_1")
    progress.on_chunk_complete("COLLECTION/IMG_2")
    progress.on_prepare_result(
        DownloadResult(image_id="COLLECTION/IMG_3", status="skipped_existing", chunk_count=4)
    )

    lines = progress.render_lines()

    # Header
    assert lines[0].startswith("━━ edown")

    # Overall progress bar line: tile counts + chunk counts
    assert "1/3 tiles" in lines[1]
    assert "3/8 chunks" in lines[1]
    assert _BAR_FILL in lines[1]

    # Timing line
    assert "elapsed" in lines[2]

    # Blank separator
    assert lines[3] == ""

    # Tile lines: each tile has icon + label + status + per-tile bar
    tile_lines = lines[_header_line_count():]
    assert any("IMG_1" in line and "2/5" in line and _BAR_FILL in line for line in tile_lines)
    assert any("IMG_2" in line and "1/3" in line and _BAR_FILL in line for line in tile_lines)
    assert any("IMG_3" in line and "cached" in line for line in tile_lines)


def test_terminal_progress_marks_failed_tile() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
    )

    progress.on_search_result(("COLLECTION/IMG_FAIL",))
    progress.on_job_prepared("COLLECTION/IMG_FAIL", 4)
    progress.on_chunk_complete("COLLECTION/IMG_FAIL")
    progress.on_job_failed("COLLECTION/IMG_FAIL", "boom")
    progress.on_job_finished(
        DownloadResult(
            image_id="COLLECTION/IMG_FAIL",
            status="failed",
            chunk_count=4,
            error="boom",
        )
    )

    lines = progress.render_lines()

    # Overall bar shows failure
    assert "1/1 tiles" in lines[1]

    # Tile shows failed status with per-tile bar
    tile_lines = lines[_header_line_count():]
    assert any("IMG_FAIL" in line and "failed" in line for line in tile_lines)
    assert any("1/4" in line and _BAR_FILL in line for line in tile_lines)
    assert any("error: boom" in line for line in tile_lines)


def test_terminal_progress_per_tile_bar_for_larger_jobs() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
    )

    progress.on_search_result(("COLLECTION/IMG_BIG",))
    progress.on_job_prepared("COLLECTION/IMG_BIG", 36)
    for _ in range(9):
        progress.on_chunk_complete("COLLECTION/IMG_BIG")

    lines = progress.render_lines()

    tile_lines = lines[_header_line_count():]
    assert any("IMG_BIG" in line and "9/36" in line for line in tile_lines)
    # Per-tile progress bar present
    assert any(
        _BAR_FILL in line and _BAR_EMPTY in line and "25%" in line for line in tile_lines
    )


def test_terminal_progress_renders_chunk_grid_shape_with_sparse_cells() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
    )

    progress.on_search_result(("COLLECTION/IMG_GRID",))
    progress.on_job_prepared("COLLECTION/IMG_GRID", 5)
    progress.on_job_chunk_grid(
        "COLLECTION/IMG_GRID",
        2,
        3,
        ((0, 0), (0, 1), (0, 2), (1, 0), (1, 2)),
    )
    progress.on_chunk_complete("COLLECTION/IMG_GRID")
    progress.on_chunk_cell_complete("COLLECTION/IMG_GRID", 0, 0)
    progress.on_chunk_complete("COLLECTION/IMG_GRID")
    progress.on_chunk_cell_complete("COLLECTION/IMG_GRID", 1, 2)

    lines = progress.render_lines()

    tile_lines = lines[_header_line_count():]
    assert any("IMG_GRID" in line and "2/5" in line and "2x3" in line for line in tile_lines)
    assert any("■□□ / □·■" in line for line in tile_lines)


def test_terminal_progress_compacts_tall_grid_preview() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
    )

    progress.on_search_result(("COLLECTION/IMG_TALL",))
    progress.on_job_prepared("COLLECTION/IMG_TALL", 8)
    progress.on_job_chunk_grid(
        "COLLECTION/IMG_TALL",
        8,
        1,
        tuple((row_index, 0) for row_index in range(8)),
    )
    for row_index in range(4):
        progress.on_chunk_complete("COLLECTION/IMG_TALL")
        progress.on_chunk_cell_complete("COLLECTION/IMG_TALL", row_index, 0)

    lines = progress.render_lines()

    tile_lines = lines[_header_line_count():]
    assert any("IMG_TALL" in line and "8x1" in line for line in tile_lines)
    # Compressed grid rows joined by " / "
    preview_lines = [line for line in tile_lines if "■" in line and "/" in line]
    assert len(preview_lines) == 1
    assert "■ /" in preview_lines[0]
    assert preview_lines[0].rstrip().endswith("/ □")


def test_terminal_progress_shows_all_active_tiles_even_above_visibility_cap() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
        max_visible_tiles=4,
    )

    image_ids = tuple(f"COLLECTION/IMG_{index}" for index in range(1, 9))
    progress.on_search_result(image_ids)
    for image_id in image_ids:
        progress.on_job_prepared(image_id, 5)

    lines = progress.render_lines()

    # Overall: 0/8 tiles, 0/40 chunks
    assert "0/8 tiles" in lines[1]
    assert "0/40 chunks" in lines[1]

    # All 8 active tiles visible
    tile_lines = lines[_header_line_count():]
    assert sum(1 for line in tile_lines if "IMG_" in line) == 8
    assert not any("…" in line for line in lines)


def test_terminal_progress_limits_non_active_tiles_after_showing_active_tiles() -> None:
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
        max_visible_tiles=4,
    )

    progress.on_search_result(
        (
            "COLLECTION/IMG_ACTIVE_1",
            "COLLECTION/IMG_ACTIVE_2",
            "COLLECTION/IMG_DONE_1",
            "COLLECTION/IMG_DONE_2",
            "COLLECTION/IMG_DONE_3",
        )
    )
    progress.on_job_prepared("COLLECTION/IMG_ACTIVE_1", 5)
    progress.on_job_prepared("COLLECTION/IMG_ACTIVE_2", 5)
    progress.on_prepare_result(
        DownloadResult(image_id="COLLECTION/IMG_DONE_1", status="downloaded", chunk_count=5)
    )
    progress.on_prepare_result(
        DownloadResult(image_id="COLLECTION/IMG_DONE_2", status="skipped_existing", chunk_count=5)
    )
    progress.on_prepare_result(
        DownloadResult(image_id="COLLECTION/IMG_DONE_3", status="downloaded", chunk_count=5)
    )

    lines = progress.render_lines()

    assert any("IMG_ACTIVE_1" in line for line in lines)
    assert any("IMG_ACTIVE_2" in line for line in lines)
    assert any("IMG_DONE_1" in line for line in lines)
    assert any("IMG_DONE_2" in line for line in lines)
    assert not any("IMG_DONE_3" in line for line in lines)
    assert any("1 more tiles queued" in line for line in lines)


def test_terminal_progress_timing_with_mock_clock() -> None:
    """Test elapsed time, speed, and ETA calculation."""
    t = 1000.0
    def clock() -> float:
        return t

    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
        clock=clock,
    )

    progress.on_search_result(("COLLECTION/IMG_1",))
    progress.on_job_prepared("COLLECTION/IMG_1", 10)

    # Simulate 5 chunks over 30 seconds
    for _ in range(5):
        t += 6.0
        progress.on_chunk_complete("COLLECTION/IMG_1")

    lines = progress.render_lines()

    # Timing line should show elapsed time and speed
    timing_line = lines[2]
    assert "elapsed 30s" in timing_line
    assert "chunks/min" in timing_line
    assert "ETA" in timing_line


def test_terminal_progress_status_icons() -> None:
    """Test that different statuses get the right icons."""
    progress = TerminalDownloadProgress(
        stream=io.StringIO(),
        enabled=False,
        terminal_width=96,
        max_visible_tiles=10,
    )

    progress.on_search_result(("COL/DONE", "COL/ACTIVE", "COL/FAIL", "COL/SKIP"))
    progress.on_job_prepared("COL/ACTIVE", 5)
    progress.on_prepare_result(
        DownloadResult(image_id="COL/SKIP", status="skipped_existing", chunk_count=0)
    )
    progress.on_job_prepared("COL/FAIL", 3)
    progress.on_job_failed("COL/FAIL", "err")
    progress.on_job_finished(
        DownloadResult(image_id="COL/FAIL", status="failed", chunk_count=3, error="err")
    )

    lines = progress.render_lines()

    tile_lines = lines[_header_line_count():]
    assert any("↓" in line and "ACTIVE" in line for line in tile_lines)
    assert any("✗" in line and "FAIL" in line for line in tile_lines)
    assert any("-" in line and "SKIP" in line for line in tile_lines)
