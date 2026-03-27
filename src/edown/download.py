from __future__ import annotations

import json
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from rasterio.windows import Window

from .auth import initialize_earth_engine
from .discovery import search_images
from .errors import DownloadError
from .grid import (
    ChunkTask,
    align_window_to_chunk,
    build_chunk_tasks,
    build_output_profile,
    calculate_optimal_chunk_size,
    get_image_grid_info,
    initialize_output_file,
    intersection_to_pixel_bounds,
    structured_to_hwc_array,
    transform_geometry_to_image_crs,
)
from .logging_utils import get_logger
from .manifest import build_manifest_document, default_manifest_path, write_manifest
from .models import DownloadConfig, DownloadResult, DownloadSummary, ImageRecord
from .plugins import load_transform_plugin
from .utils import default_nodata_for_dtype, mapping_value_for_band_id, output_tree_paths


@dataclass
class _PreparedJob:
    image: ImageRecord
    grid: dict[str, Any]
    row0: int
    row1: int
    col0: int
    col1: int
    chunk_size: int
    tasks: List[ChunkTask]
    out_path: Path
    metadata_path: Path
    dataset: Any
    nodata: Any
    expression: Optional[Any]


@dataclass(frozen=True)
class _PrepareOutcome:
    job: Optional[_PreparedJob] = None
    result: Optional[DownloadResult] = None


def _prepare_job_safe(image: ImageRecord, config: DownloadConfig) -> _PrepareOutcome:
    try:
        return _prepare_job(image, config)
    except Exception as exc:
        return _PrepareOutcome(
            result=DownloadResult(
                image_id=image.image_id,
                status="failed",
                error=f"Preparation failed: {exc}",
            )
        )


def _write_metadata_sidecar(metadata_path: Path, image_info: dict[str, Any]) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(image_info, indent=2), encoding="utf-8")


def _build_requested_image(image: ImageRecord, config: DownloadConfig) -> Optional[Any]:
    if not config.scale_map and not config.transform_plugin:
        return None

    import ee

    plugin = load_transform_plugin(config.transform_plugin)
    ee_image = ee.Image(image.image_id)
    if plugin is not None:
        ee_image = plugin(ee_image, image.raw_image_info, config)
    ee_image = ee_image.select(list(image.selected_band_ids))
    for band_id in image.selected_band_ids:
        scale = mapping_value_for_band_id(band_id, config.scale_map)
        if scale is not None:
            scaled = ee_image.select([band_id]).multiply(float(scale)).rename([band_id])
            ee_image = ee_image.addBands(scaled, overwrite=True)
    return ee_image


def _prepare_job(image: ImageRecord, config: DownloadConfig) -> _PrepareOutcome:
    if image.missing_band_ids:
        return _PrepareOutcome(
            result=DownloadResult(
                image_id=image.image_id,
                status="skipped_missing_bands",
                error="Missing requested bands: " + ", ".join(image.missing_band_ids),
            )
        )

    grid = get_image_grid_info(image.raw_image_info)
    aoi_geometry = transform_geometry_to_image_crs(config.aoi.geometry, grid["crs"])
    intersection = grid["bbox"].intersection(aoi_geometry)
    pixel_bounds = intersection_to_pixel_bounds(intersection, grid)
    if pixel_bounds is None:
        return _PrepareOutcome(
            result=DownloadResult(
                image_id=image.image_id,
                status="skipped_outside_aoi",
                error="Image does not intersect the AOI after native-grid clipping.",
            )
        )

    requested_chunk_size = config.chunk_size if config.chunk_size_mode == "fixed" else None
    chunk_size = calculate_optimal_chunk_size(
        grid=grid,
        pixel_bounds=pixel_bounds,
        band_byte_sizes=image.band_byte_sizes,
        requested_chunk_size=requested_chunk_size,
        request_byte_limit=config.request_byte_limit,
    )
    row0, row1, col0, col1 = align_window_to_chunk(pixel_bounds, grid, chunk_size)
    tasks = build_chunk_tasks(
        row0=row0,
        row1=row1,
        col0=col0,
        col1=col1,
        grid=grid,
        intersection=intersection,
        chunk_size=chunk_size,
    )
    if not tasks:
        return _PrepareOutcome(
            result=DownloadResult(
                image_id=image.image_id,
                status="skipped_outside_aoi",
                error="No intersecting chunks were generated for the AOI.",
            )
        )

    out_path, metadata_path = output_tree_paths(
        config.output_root,
        image.collection_id,
        image.image_id,
    )
    if config.resume and not config.overwrite and out_path.exists() and metadata_path.exists():
        return _PrepareOutcome(
            result=DownloadResult(
                image_id=image.image_id,
                status="skipped_existing",
                tiff_path=out_path,
                metadata_path=metadata_path,
                chunk_count=len(tasks),
            )
        )

    if config.overwrite:
        if out_path.exists():
            out_path.unlink()
        if metadata_path.exists():
            metadata_path.unlink()

    nodata = (
        config.nodata
        if config.nodata is not None
        else default_nodata_for_dtype(image.output_dtype)
    )
    profile = build_output_profile(
        grid=grid,
        row0=row0,
        col0=col0,
        width=col1 - col0,
        height=row1 - row0,
        band_count=len(image.selected_band_ids),
        dtype_name=image.output_dtype,
        nodata=nodata,
    )
    dataset = initialize_output_file(
        out_path=out_path,
        profile=profile,
        image_info=image.raw_image_info,
        band_descriptions=image.output_band_names,
        chunk_size=chunk_size,
        nodata=nodata,
    )
    expression = _build_requested_image(image, config)
    return _PrepareOutcome(
        job=_PreparedJob(
            image=image,
            grid=grid,
            row0=row0,
            row1=row1,
            col0=col0,
            col1=col1,
            chunk_size=chunk_size,
            tasks=tasks,
            out_path=out_path,
            metadata_path=metadata_path,
            dataset=dataset,
            nodata=nodata,
            expression=expression,
        )
    )


def _fetch_chunk(
    job: _PreparedJob, task: ChunkTask, config: DownloadConfig
) -> Tuple[int, int, NDArray[np.generic]]:
    import ee

    row, col, chunk_h, chunk_w = task
    request = {
        "fileFormat": "NUMPY_NDARRAY",
        "bandIds": list(job.image.selected_band_ids),
        "grid": {
            "dimensions": {"width": int(chunk_w), "height": int(chunk_h)},
            "crsCode": job.grid["crs"],
            "affineTransform": {
                "scaleX": job.grid["x_scale"],
                "shearX": 0,
                "translateX": job.grid["origin_x"] + col * job.grid["x_scale"],
                "shearY": 0,
                "scaleY": job.grid["y_scale"],
                "translateY": job.grid["origin_y"] + row * job.grid["y_scale"],
            },
        },
    }
    if job.expression is None:
        request["assetId"] = job.image.image_id
    else:
        request["expression"] = job.expression

    delay_seconds = config.retry_delay_seconds
    for attempt in range(1, config.max_retries + 1):
        try:
            raw = (
                ee.data.getPixels(request)
                if "assetId" in request
                else ee.data.computePixels(request)
            )
            data = np.array(
                structured_to_hwc_array(raw, job.image.selected_band_ids),
                dtype=np.dtype(job.image.output_dtype),
                copy=True,
            )
            return row, col, data
        except Exception:
            if attempt == config.max_retries:
                raise
            time.sleep(delay_seconds)
            delay_seconds *= 2
    raise DownloadError("Unexpected retry termination while downloading chunks.")


def _submit_pending_tasks(
    executor: ThreadPoolExecutor,
    task_queue: Deque[Tuple[_PreparedJob, ChunkTask]],
    pending: Dict[Future[Tuple[int, int, NDArray[np.generic]]], Tuple[_PreparedJob, ChunkTask]],
    failed_jobs: set[str],
    max_inflight: int,
    config: DownloadConfig,
) -> None:
    while task_queue and len(pending) < max_inflight:
        job, task = task_queue.popleft()
        if job.image.image_id in failed_jobs:
            continue
        future = executor.submit(_fetch_chunk, job, task, config)
        pending[future] = (job, task)


def download_images(config: DownloadConfig) -> DownloadSummary:
    logger = get_logger("edown.download")
    initialize_earth_engine(config.server_url)
    search_result = search_images(config)

    prepare_outcomes: list[_PrepareOutcome] = []
    with ThreadPoolExecutor(max_workers=max(1, config.prepare_workers)) as executor:
        prepare_futures = [
            executor.submit(_prepare_job_safe, image, config) for image in search_result.images
        ]
        for prepare_future in prepare_futures:
            prepare_outcomes.append(prepare_future.result())

    prepared_jobs: list[_PreparedJob] = []
    results: list[DownloadResult] = []
    for outcome in prepare_outcomes:
        if outcome.result is not None:
            results.append(outcome.result)
        elif outcome.job is not None:
            prepared_jobs.append(outcome.job)

    failed_jobs: set[str] = set()
    failure_messages: dict[str, str] = {}
    task_queue: Deque[Tuple[_PreparedJob, ChunkTask]] = deque(
        (job, task) for job in prepared_jobs for task in job.tasks
    )
    max_inflight = max(config.download_workers, config.max_inflight_chunks)

    try:
        with ThreadPoolExecutor(max_workers=max(1, config.download_workers)) as executor:
            pending: Dict[
                Future[Tuple[int, int, NDArray[np.generic]]],
                Tuple[_PreparedJob, ChunkTask],
            ] = {}
            _submit_pending_tasks(executor, task_queue, pending, failed_jobs, max_inflight, config)

            while pending:
                done, _ = wait(tuple(pending.keys()), return_when=FIRST_COMPLETED)
                for chunk_future in done:
                    job, _task = pending.pop(chunk_future)
                    try:
                        row, col, data = chunk_future.result()
                        job.dataset.write(
                            np.moveaxis(data, -1, 0),
                            window=Window(
                                col - job.col0,
                                row - job.row0,
                                data.shape[1],
                                data.shape[0],
                            ),
                        )
                    except Exception as exc:
                        failed_jobs.add(job.image.image_id)
                        failure_messages[job.image.image_id] = str(exc)
                        logger.exception("Failed to download chunks for %s", job.image.image_id)
                    _submit_pending_tasks(
                        executor,
                        task_queue,
                        pending,
                        failed_jobs,
                        max_inflight,
                        config,
                    )
    finally:
        for job in prepared_jobs:
            try:
                if not job.dataset.closed:
                    job.dataset.close()
            except Exception:
                pass

    for job in prepared_jobs:
        if job.image.image_id in failed_jobs:
            if job.out_path.exists():
                job.out_path.unlink()
            if job.metadata_path.exists():
                job.metadata_path.unlink()
            results.append(
                DownloadResult(
                    image_id=job.image.image_id,
                    status="failed",
                    chunk_count=len(job.tasks),
                    error=failure_messages.get(job.image.image_id, "Unknown download failure."),
                )
            )
            continue

        _write_metadata_sidecar(job.metadata_path, job.image.raw_image_info)
        results.append(
            DownloadResult(
                image_id=job.image.image_id,
                status="downloaded",
                tiff_path=job.out_path,
                metadata_path=job.metadata_path,
                chunk_count=len(job.tasks),
            )
        )

    results = sorted(results, key=lambda item: item.image_id)
    manifest_path = config.manifest_path or default_manifest_path(config.output_root)
    summary = DownloadSummary(
        manifest_path=manifest_path,
        output_root=config.output_root,
        results=tuple(results),
    )
    document = build_manifest_document(config, search_result, download_summary=summary)
    write_manifest(manifest_path, document)
    return summary
