from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .auth import initialize_earth_engine
from .constants import PRECISION_TO_DTYPE
from .errors import DiscoveryError
from .grid import get_image_grid_info
from .logging_utils import get_logger
from .models import AlignmentGroup, ImageRecord, SearchConfig, SearchResult
from .utils import (
    alignment_signature,
    band_output_names,
    inclusive_date_range_to_exclusive_end,
    promote_dtype_name,
    relative_tiff_path,
    resolve_requested_band_id,
    utc_now,
)


def parse_gee_acquisition_time(image_info: Mapping[str, Any]) -> datetime:
    time_start = image_info.get("properties", {}).get("system:time_start")
    if time_start is None:
        raise DiscoveryError(f"GEE image {image_info.get('id')} has no system:time_start")
    return datetime.fromtimestamp(float(time_start) / 1000.0, tz=timezone.utc)


def estimate_local_datetime(acquisition_time_utc: datetime, bounds: Sequence[float]) -> datetime:
    center_longitude = (bounds[0] + bounds[2]) / 2
    return acquisition_time_utc.replace(tzinfo=None) + timedelta(hours=center_longitude / 15.0)


def discover_bands(
    config: SearchConfig, representative_image: Mapping[str, Any]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    available = [band["id"] for band in representative_image["bands"]]
    if config.bands:
        chosen = []
        for band in config.bands:
            resolved = resolve_requested_band_id(band, available)
            if resolved is not None and resolved not in chosen:
                chosen.append(resolved)
    else:
        chosen = []
        for band in available:
            include_ok = True if not config.band_include else any(
                re.search(pattern, band) for pattern in config.band_include
            )
            exclude_hit = any(re.search(pattern, band) for pattern in config.band_exclude)
            if include_ok and not exclude_hit:
                chosen.append(band)
    if not chosen:
        raise DiscoveryError(
            "No bands selected from collection "
            f"{config.collection_id}. Available bands: {available}"
        )
    return tuple(chosen), band_output_names(chosen, config.rename_map)


def precision_to_numpy_dtype_name(
    available_band_ids: Iterable[str],
    band_precisions: Mapping[str, str],
    scale_map_present: bool,
    transform_plugin_present: bool,
) -> str:
    if scale_map_present or transform_plugin_present:
        return "float32"
    chosen = [
        PRECISION_TO_DTYPE.get(band_precisions[band_id], "float32")
        for band_id in available_band_ids
    ]
    if not chosen:
        return "float32"
    maximum = max(chosen, key=lambda value: np.dtype(value).itemsize)
    return promote_dtype_name(maximum)


def alignment_groups_for_images(images: Sequence[ImageRecord]) -> tuple[AlignmentGroup, ...]:
    grouped: dict[str, list[ImageRecord]] = defaultdict(list)
    for image in images:
        if image.missing_band_ids:
            continue
        grouped[image.alignment_signature].append(image)

    groups: list[AlignmentGroup] = []
    for group_id, group_images in grouped.items():
        group_images = sorted(group_images, key=lambda item: item.acquisition_time_utc)
        first = group_images[0]
        groups.append(
            AlignmentGroup(
                group_id=group_id,
                image_ids=tuple(image.image_id for image in group_images),
                crs=first.native_crs,
                transform=first.native_transform,
                width=first.native_width,
                height=first.native_height,
                band_names=first.output_band_names,
                dtype=first.output_dtype,
            )
        )
    return tuple(sorted(groups, key=lambda item: item.group_id))


def _build_collection(config: SearchConfig, start: datetime, end: datetime) -> Any:
    import ee

    collection = ee.ImageCollection(config.collection_id)
    collection = collection.filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    collection = collection.filterBounds(config.aoi.to_ee_geometry())
    return collection


def _count_features_for_range(config: SearchConfig, start: datetime, end: datetime) -> int:
    collection = _build_collection(config, start, end)
    return int(collection.size().getInfo())


def _get_features_for_range(
    config: SearchConfig, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    logger = get_logger("edown.discovery")
    collection = _build_collection(config, start, end)
    info = collection.getInfo()
    features = info.get("features", [])
    logger.debug("Fetched %d features for %s..%s", len(features), start, end)
    return list(features)


def _collect_features_for_range(
    config: SearchConfig, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    count = _count_features_for_range(config, start, end)
    if count == 0:
        return []
    if count <= config.collection_chunk_limit or (end - start).days <= 1:
        return _get_features_for_range(config, start, end)

    midpoint = start + (end - start) / 2
    midpoint = midpoint.replace(hour=0, minute=0, second=0, microsecond=0)
    if midpoint <= start:
        midpoint = start + timedelta(days=1)
    if midpoint >= end:
        return _get_features_for_range(config, start, end)

    left = _collect_features_for_range(config, start, midpoint)
    right = _collect_features_for_range(config, midpoint, end)
    deduped = {feature["id"]: feature for feature in left + right}
    return list(deduped.values())


def search_images(config: SearchConfig) -> SearchResult:
    logger = get_logger("edown.discovery")
    initialize_earth_engine(config.server_url)
    start_date, end_exclusive = inclusive_date_range_to_exclusive_end(
        config.start_date, config.end_date
    )
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_exclusive, datetime.min.time(), tzinfo=timezone.utc)

    features = _collect_features_for_range(config, start_dt, end_dt)
    features = sorted(features, key=lambda item: item["properties"]["system:time_start"])
    if not features:
        raise DiscoveryError(
            f"No images found in {config.collection_id} for {config.start_date}..{config.end_date}"
        )

    selected_band_ids, output_band_names = discover_bands(config, features[0])
    logger.info("Discovered %d images", len(features))

    images: list[ImageRecord] = []
    for feature in features:
        grid = get_image_grid_info(feature)
        available_band_ids = tuple(band["id"] for band in feature["bands"])
        band_precisions = {
            band["id"]: band.get("data_type", {}).get("precision", "float32")
            for band in feature["bands"]
        }
        missing = tuple(band for band in selected_band_ids if band not in available_band_ids)
        available_selected = tuple(band for band in selected_band_ids if band in available_band_ids)
        band_byte_sizes = {
            band_id: int(
                np.dtype(PRECISION_TO_DTYPE.get(band_precisions[band_id], "float32")).itemsize
            )
            for band_id in available_selected
        }
        output_dtype = precision_to_numpy_dtype_name(
            available_selected,
            band_precisions,
            scale_map_present=bool(config.scale_map),
            transform_plugin_present=bool(config.transform_plugin),
        )
        acquisition_time_utc = parse_gee_acquisition_time(feature)
        alignment_payload = {
            "crs": grid["crs"],
            "transform": tuple(float(value) for value in grid["transform"]),
            "width": grid["width"],
            "height": grid["height"],
            "bands": output_band_names,
            "dtype": output_dtype,
        }
        images.append(
            ImageRecord(
                collection_id=config.collection_id,
                image_id=feature["id"],
                acquisition_time_utc=acquisition_time_utc,
                local_datetime=estimate_local_datetime(acquisition_time_utc, config.aoi.bounds),
                properties=dict(feature.get("properties", {})),
                raw_image_info=dict(feature),
                available_band_ids=available_band_ids,
                selected_band_ids=selected_band_ids,
                output_band_names=output_band_names,
                missing_band_ids=missing,
                band_byte_sizes=band_byte_sizes,
                output_dtype=output_dtype,
                native_crs=grid["crs"],
                native_transform=tuple(float(value) for value in grid["transform"]),
                native_width=int(grid["width"]),
                native_height=int(grid["height"]),
                native_bounds=(
                    float(grid["bbox"].bounds[0]),
                    float(grid["bbox"].bounds[1]),
                    float(grid["bbox"].bounds[2]),
                    float(grid["bbox"].bounds[3]),
                ),
                alignment_signature=alignment_signature(alignment_payload),
                relative_tiff_path=relative_tiff_path(config.collection_id, feature["id"]),
            )
        )

    return SearchResult(
        collection_id=config.collection_id,
        start_date=config.start_date,
        end_date=config.end_date,
        aoi_bounds=config.aoi.bounds,
        selected_band_ids=selected_band_ids,
        output_band_names=output_band_names,
        images=tuple(images),
        alignment_groups=alignment_groups_for_images(images),
        created_at=utc_now(),
    )
