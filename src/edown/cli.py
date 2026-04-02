from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, TypeVar

import click

from .aoi import AOI
from .constants import (
    DEFAULT_DOWNLOAD_WORKERS,
    DEFAULT_MAX_INFLIGHT_CHUNKS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PREPARE_WORKERS,
    DEFAULT_REQUEST_BYTE_LIMIT,
    DEFAULT_RETRY_DELAY_SECONDS,
)
from .discovery import search_images
from .download import download_images
from .logging_utils import configure_logging
from .manifest import build_manifest_document, default_manifest_path, write_manifest
from .models import DownloadConfig, SearchConfig, StackConfig
from .progress import TerminalDownloadProgress
from .stack import stack_images
from .utils import split_csv_values

F = TypeVar("F", bound=Callable[..., Any])


def _json_dict(
    _ctx: click.Context, _param: click.Parameter, value: Optional[str]
) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(str(exc)) from exc
    if not isinstance(decoded, dict):
        raise click.BadParameter("value must decode to a JSON object")
    return decoded


def _format_download_summary(summary: Any) -> str:
    line = f"Downloaded={summary.downloaded} Skipped={summary.skipped} Failed={summary.failed}"
    skip_counts = Counter(
        result.status for result in summary.results if result.status.startswith("skipped")
    )
    if skip_counts:
        details = ", ".join(
            f"{status}={count}" for status, count in sorted(skip_counts.items())
        )
        line = f"{line} ({details})"
    return line


def _build_download_progress() -> Optional[TerminalDownloadProgress]:
    stream = click.get_text_stream("stderr")
    term = os.environ.get("TERM", "").strip().lower()
    if not stream.isatty() or not term or term == "dumb":
        return None
    return TerminalDownloadProgress(stream=stream)


def _common_collection_options(command: F) -> F:
    for option in reversed(
        [
            click.option("--collection-id", required=True, help="Earth Engine ImageCollection id."),
            click.option("--start-date", required=True, help="Inclusive start date YYYY-MM-DD."),
            click.option("--end-date", required=True, help="Inclusive end date YYYY-MM-DD."),
            click.option(
                "--bbox",
                nargs=4,
                type=float,
                default=None,
                help="AOI bounding box xmin ymin xmax ymax in WGS84.",
            ),
            click.option(
                "--geojson",
                "geojson_path",
                type=click.Path(exists=True, dir_okay=False, path_type=Path),
                default=None,
                help="AOI GeoJSON path.",
            ),
            click.option(
                "--band",
                "bands",
                multiple=True,
                help="Band id to request; repeat or use commas.",
            ),
            click.option(
                "--band-include",
                multiple=True,
                help="Regex include filter for auto-discovered bands.",
            ),
            click.option(
                "--band-exclude",
                multiple=True,
                help="Regex exclude filter for auto-discovered bands.",
            ),
            click.option(
                "--rename-map",
                callback=_json_dict,
                default=None,
                help='JSON object such as {"B4": "red"}',
            ),
            click.option(
                "--scale-map",
                callback=_json_dict,
                default=None,
                help='JSON object such as {"B4": 0.0001}',
            ),
            click.option(
                "--transform-plugin",
                default=None,
                help="Optional transform plugin in the form module:function",
            ),
            click.option(
                "--server-url",
                default="https://earthengine-highvolume.googleapis.com",
                show_default=True,
                help="Earth Engine API URL.",
            ),
        ]
    ):
        command = option(command)
    return command


def _build_aoi(
    bbox: Optional[Tuple[float, float, float, float]],
    geojson_path: Optional[Path],
) -> AOI:
    return AOI.from_inputs(bbox=bbox, geojson_path=geojson_path)


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def main(verbose: bool) -> None:
    configure_logging(verbose=verbose)


@main.command("search")
@_common_collection_options
@click.option(
    "--manifest-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path for the output manifest.",
)
def search_command(
    collection_id: str,
    start_date: str,
    end_date: str,
    bbox: Optional[Tuple[float, float, float, float]],
    geojson_path: Optional[Path],
    bands: Tuple[str, ...],
    band_include: Tuple[str, ...],
    band_exclude: Tuple[str, ...],
    rename_map: Optional[dict[str, Any]],
    scale_map: Optional[dict[str, Any]],
    transform_plugin: Optional[str],
    server_url: str,
    manifest_path: Optional[Path],
) -> None:
    config = SearchConfig(
        collection_id=collection_id,
        start_date=start_date,
        end_date=end_date,
        aoi=_build_aoi(bbox, geojson_path),
        bands=split_csv_values(bands),
        band_include=band_include,
        band_exclude=band_exclude,
        rename_map={str(key): str(value) for key, value in (rename_map or {}).items()},
        scale_map={str(key): float(value) for key, value in (scale_map or {}).items()},
        transform_plugin=transform_plugin,
        server_url=server_url,
    )
    result = search_images(config)
    output_manifest = manifest_path or default_manifest_path(Path("."))
    write_manifest(output_manifest, build_manifest_document(config, result))
    click.echo(f"Discovered {len(result.images)} images")
    click.echo(str(output_manifest))


@main.command("download")
@_common_collection_options
@click.option(
    "--output-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
)
@click.option(
    "--manifest-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
@click.option("--chunk-size", type=int, default=None, help="Chunk size override.")
@click.option(
    "--chunk-size-mode",
    type=click.Choice(["auto", "fixed"]),
    default="auto",
    show_default=True,
)
@click.option("--prepare-workers", default=DEFAULT_PREPARE_WORKERS, show_default=True, type=int)
@click.option("--download-workers", default=DEFAULT_DOWNLOAD_WORKERS, show_default=True, type=int)
@click.option("--max-inflight-chunks", default=DEFAULT_MAX_INFLIGHT_CHUNKS, show_default=True, type=int)
@click.option("--max-retries", default=DEFAULT_MAX_RETRIES, show_default=True, type=int)
@click.option("--retry-delay-seconds", default=DEFAULT_RETRY_DELAY_SECONDS, show_default=True, type=float)
@click.option(
    "--request-byte-limit",
    default=DEFAULT_REQUEST_BYTE_LIMIT,
    show_default=True,
    type=int,
)
@click.option(
    "--nodata",
    default=None,
    type=float,
    help="Optional nodata value for output GeoTIFFs.",
)
@click.option("--overwrite/--no-overwrite", default=False, show_default=True)
@click.option("--resume/--no-resume", default=True, show_default=True)
def download_command(
    collection_id: str,
    start_date: str,
    end_date: str,
    bbox: Optional[Tuple[float, float, float, float]],
    geojson_path: Optional[Path],
    bands: Tuple[str, ...],
    band_include: Tuple[str, ...],
    band_exclude: Tuple[str, ...],
    rename_map: Optional[dict[str, Any]],
    scale_map: Optional[dict[str, Any]],
    transform_plugin: Optional[str],
    server_url: str,
    output_root: Path,
    manifest_path: Optional[Path],
    chunk_size: Optional[int],
    chunk_size_mode: str,
    prepare_workers: int,
    download_workers: int,
    max_inflight_chunks: int,
    max_retries: int,
    retry_delay_seconds: float,
    request_byte_limit: int,
    nodata: Optional[float],
    overwrite: bool,
    resume: bool,
) -> None:
    config = DownloadConfig(
        collection_id=collection_id,
        start_date=start_date,
        end_date=end_date,
        aoi=_build_aoi(bbox, geojson_path),
        bands=split_csv_values(bands),
        band_include=band_include,
        band_exclude=band_exclude,
        rename_map={str(key): str(value) for key, value in (rename_map or {}).items()},
        scale_map={str(key): float(value) for key, value in (scale_map or {}).items()},
        transform_plugin=transform_plugin,
        server_url=server_url,
        output_root=output_root,
        manifest_path=manifest_path,
        chunk_size=chunk_size,
        chunk_size_mode=chunk_size_mode,
        prepare_workers=prepare_workers,
        download_workers=download_workers,
        max_inflight_chunks=max_inflight_chunks,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
        request_byte_limit=request_byte_limit,
        nodata=nodata,
        overwrite=overwrite,
        resume=resume,
    )
    summary = download_images(config, progress=_build_download_progress())
    click.echo(f"Manifest: {summary.manifest_path}")
    click.echo(_format_download_summary(summary))
    if summary.failed:
        raise click.ClickException("One or more images failed to download.")


@main.command("stack")
@click.option(
    "--manifest-path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--output-root", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option(
    "--backend",
    type=click.Choice(["threads", "dask-local", "dask-slurm"]),
    default="threads",
    show_default=True,
)
@click.option("--overwrite/--no-overwrite", default=False, show_default=True)
@click.option("--n-workers", default=4, show_default=True, type=int)
@click.option("--cores-per-worker", default=1, show_default=True, type=int)
@click.option("--memory-per-worker", default="1GB", show_default=True)
@click.option("--slurm-queue", default=None)
@click.option("--slurm-account", default=None)
def stack_command(
    manifest_path: Path,
    output_root: Optional[Path],
    backend: str,
    overwrite: bool,
    n_workers: int,
    cores_per_worker: int,
    memory_per_worker: str,
    slurm_queue: Optional[str],
    slurm_account: Optional[str],
) -> None:
    config = StackConfig(
        manifest_path=manifest_path,
        output_root=output_root,
        backend=backend,
        overwrite=overwrite,
        n_workers=n_workers,
        cores_per_worker=cores_per_worker,
        memory_per_worker=memory_per_worker,
        slurm_queue=slurm_queue,
        slurm_account=slurm_account,
    )
    results = stack_images(config)
    for result in results:
        if result.output_path is not None and result.skipped_reason is None:
            click.echo(f"{result.group_id}: {result.output_path}")
        else:
            click.echo(f"{result.group_id}: skipped ({result.skipped_reason})")
