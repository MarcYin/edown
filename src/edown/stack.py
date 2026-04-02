from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .errors import StackError
from .logging_utils import get_logger
from .manifest import build_manifest_document, load_manifest, write_manifest
from .models import SearchResult, StackConfig, StackResult
from .utils import safe_identifier


def _read_tiff_array(path: Path) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as dataset:
        return dataset.read()


def _read_tiff_grid(path: Path) -> tuple[tuple[float, ...], int, int, Optional[str]]:
    import rasterio

    with rasterio.open(path) as dataset:
        transform = dataset.transform
        crs = dataset.crs.to_string() if dataset.crs is not None else None
        return (
            (
                float(transform.a),
                float(transform.b),
                float(transform.c),
                float(transform.d),
                float(transform.e),
                float(transform.f),
            ),
            int(dataset.width),
            int(dataset.height),
            crs,
        )


def _x_y_coords(
    transform: tuple[float, ...], width: int, height: int
) -> tuple[np.ndarray, np.ndarray]:
    scale_x, _shear_x, translate_x, _shear_y, scale_y, translate_y = transform
    x_coords = translate_x + scale_x * (np.arange(width) + 0.5)
    y_coords = translate_y + scale_y * (np.arange(height) + 0.5)
    return x_coords, y_coords


@contextmanager
def _dask_client(config: StackConfig) -> Iterator[Optional[Any]]:
    if config.backend == "threads":
        yield None
        return

    client: Optional[Any] = None
    cluster: Optional[Any] = None
    try:
        if config.backend == "dask-local":
            from distributed import Client as LocalClient
            from distributed import LocalCluster

            cluster = LocalCluster(
                n_workers=config.n_workers,
                threads_per_worker=config.cores_per_worker,
                processes=True,
                dashboard_address=None,
            )
            client = LocalClient(cluster)
        else:
            from dask.distributed import Client as SlurmClient
            from dask_jobqueue import SLURMCluster as SlurmClusterClass

            slurm_cluster_cls: Any = SlurmClusterClass

            cluster_kwargs: dict[str, object] = {
                "queue": config.slurm_queue,
                "cores": config.cores_per_worker,
                "memory": config.memory_per_worker,
            }
            if config.slurm_account:
                cluster_kwargs["account"] = config.slurm_account
            cluster = slurm_cluster_cls(
                **{key: value for key, value in cluster_kwargs.items() if value is not None}
            )
            cluster.scale(config.n_workers)
            client = SlurmClient(cluster)
        yield client
    finally:
        if client is not None:
            client.close()
        if cluster is not None:
            cluster.close()


def _build_search_result_from_manifest(document: dict[str, Any]) -> SearchResult:
    from datetime import datetime

    from .models import AlignmentGroup, ImageRecord

    search = document["search"]
    images = []
    for image in search["images"]:
        images.append(
            ImageRecord(
                collection_id=image["collection_id"],
                image_id=image["image_id"],
                acquisition_time_utc=datetime.fromisoformat(image["acquisition_time_utc"]),
                local_datetime=datetime.fromisoformat(image["local_datetime"]),
                properties=image["properties"],
                raw_image_info=image["raw_image_info"],
                available_band_ids=tuple(image["available_band_ids"]),
                selected_band_ids=tuple(image["selected_band_ids"]),
                output_band_names=tuple(image["output_band_names"]),
                missing_band_ids=tuple(image["missing_band_ids"]),
                band_byte_sizes=dict(image["band_byte_sizes"]),
                output_dtype=image["output_dtype"],
                native_crs=image["native_crs"],
                native_transform=tuple(image["native_transform"]),
                native_width=int(image["native_width"]),
                native_height=int(image["native_height"]),
                native_bounds=tuple(image["native_bounds"]),
                alignment_signature=image["alignment_signature"],
                relative_tiff_path=image["relative_tiff_path"],
            )
        )
    alignment_groups = []
    for group in search["alignment_groups"]:
        alignment_groups.append(
            AlignmentGroup(
                group_id=group["group_id"],
                image_ids=tuple(group["image_ids"]),
                crs=group["crs"],
                transform=tuple(group["transform"]),
                width=int(group["width"]),
                height=int(group["height"]),
                band_names=tuple(group["band_names"]),
                dtype=group["dtype"],
            )
        )
    return SearchResult(
        collection_id=search["collection_id"],
        start_date=search["start_date"],
        end_date=search["end_date"],
        aoi_bounds=tuple(search["aoi_bounds"]),
        selected_band_ids=tuple(search["selected_band_ids"]),
        output_band_names=tuple(search["output_band_names"]),
        images=tuple(images),
        alignment_groups=tuple(alignment_groups),
        created_at=datetime.fromisoformat(search["created_at"]),
    )


def stack_images(config: StackConfig) -> list[StackResult]:
    logger = get_logger("edown.stack")
    document = load_manifest(config.manifest_path)
    search_result = _build_search_result_from_manifest(document)
    download = document.get("download")
    if not download:
        raise StackError("Manifest does not contain download results.")

    result_by_image_id = {result["image_id"]: result for result in download["results"]}
    image_by_id = {image.image_id: image for image in search_result.images}
    default_root = Path(download["output_root"])
    output_root = config.output_root or default_root
    stack_root = output_root / "stacks" / safe_identifier(search_result.collection_id)

    results: list[StackResult] = []
    with _dask_client(config):
        for group in search_result.alignment_groups:
            group_images = []
            for image_id in group.image_ids:
                result = result_by_image_id.get(image_id)
                if result is None:
                    continue
                if result["status"] not in {"downloaded", "skipped_existing"}:
                    continue
                image = image_by_id.get(image_id)
                if image is None:
                    continue
                group_images.append((image, Path(result["tiff_path"])))

            if not group_images:
                results.append(
                    StackResult(
                        group_id=group.group_id,
                        image_count=0,
                        skipped_reason="No downloaded images available for this alignment group.",
                    )
                )
                continue

            stack_root.mkdir(parents=True, exist_ok=True)
            zarr_path = stack_root / f"{group.group_id}.zarr"
            if zarr_path.exists():
                if not config.overwrite:
                    results.append(
                        StackResult(
                            group_id=group.group_id,
                            image_count=len(group_images),
                            output_path=zarr_path,
                            skipped_reason="Stack already exists.",
                        )
                    )
                    continue
                shutil.rmtree(zarr_path)

            _first_image, first_path = group_images[0]
            stack_transform, stack_width, stack_height, stack_crs = _read_tiff_grid(first_path)
            x_coords, y_coords = _x_y_coords(
                stack_transform,
                stack_width,
                stack_height,
            )
            time_coords = np.array(
                [
                    image.acquisition_time_utc.replace(tzinfo=None)
                    for image, _path in group_images
                ],
                dtype="datetime64[ns]",
            )

            try:
                import xarray as xr

                if config.backend == "threads":
                    arrays = [_read_tiff_array(path) for _image, path in group_images]
                    data = np.stack(arrays, axis=0)
                else:
                    import dask.array as da
                    from dask import delayed

                    sample = _read_tiff_array(first_path)
                    delayed_arrays = [
                        da.from_delayed(
                            delayed(_read_tiff_array)(path),
                            shape=sample.shape,
                            dtype=np.dtype(group.dtype),
                        )
                        for _image, path in group_images
                    ]
                    data = da.stack(delayed_arrays, axis=0)

                data_array = xr.DataArray(
                    data,
                    dims=("time", "band", "y", "x"),
                    coords={
                        "time": ("time", time_coords),
                        "band": list(group.band_names),
                        "y": y_coords,
                        "x": x_coords,
                    },
                    name="data",
                    attrs={
                        "crs": stack_crs or group.crs,
                        "transform": stack_transform,
                    },
                )
                dataset = xr.Dataset({"data": data_array})
                dataset.to_zarr(zarr_path, mode="w")
                results.append(
                    StackResult(
                        group_id=group.group_id,
                        image_count=len(group_images),
                        output_path=zarr_path,
                    )
                )
            except Exception as exc:
                logger.exception("Failed to build stack for group %s", group.group_id)
                results.append(
                    StackResult(
                        group_id=group.group_id,
                        image_count=len(group_images),
                        skipped_reason=str(exc),
                    )
                )

    updated = build_manifest_document(
        config=document["config"],
        search_result=search_result,
        download_summary=None,
        stack_results=results,
        stack_config=config,
    )
    updated["download"] = document["download"]
    write_manifest(config.manifest_path, updated)
    return results
