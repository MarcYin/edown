from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import Affine
from rasterio.windows import Window
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from .constants import DEFAULT_BLOCK_SIZE

GridInfo = dict[str, Any]
PixelBounds = tuple[int, int, int, int]
ChunkTask = tuple[int, int, int, int]


def structured_to_hwc_array(raw: np.ndarray, bands: Sequence[str]) -> np.ndarray:
    if getattr(raw.dtype, "names", None):
        return np.stack([raw[band] for band in bands], axis=-1)
    array = np.asarray(raw)
    if array.ndim == 2 and len(bands) == 1:
        array = array[:, :, None]
    return array


def transform_geometry_to_image_crs(geometry: BaseGeometry, dst_crs: str) -> BaseGeometry:
    transformer = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
    transformed = shapely_transform(transformer.transform, geometry)
    if transformed.is_empty:
        raise ValueError("AOI is empty after transformation.")
    if not transformed.is_valid:
        transformed = transformed.buffer(0)
    return transformed


def get_image_grid_info(image_info: Mapping[str, Any]) -> GridInfo:
    band0 = image_info["bands"][0]
    transform = band0["crs_transform"]
    if len(transform) != 6:
        raise ValueError("Image grid transform must contain six values.")
    width, height = band0["dimensions"]
    if transform[1] != 0 or transform[3] != 0:
        raise NotImplementedError("Only north-up images without shear are supported.")

    x_scale = float(transform[0])
    y_scale = float(transform[4])
    origin_x = float(transform[2])
    origin_y = float(transform[5])
    x2 = origin_x + x_scale * width
    y2 = origin_y + y_scale * height
    return {
        "crs": band0["crs"],
        "transform": tuple(float(value) for value in transform),
        "x_scale": x_scale,
        "y_scale": y_scale,
        "pixel_w": abs(x_scale),
        "pixel_h": abs(y_scale),
        "origin_x": origin_x,
        "origin_y": origin_y,
        "width": int(width),
        "height": int(height),
        "bbox": box(
            min(origin_x, x2),
            min(origin_y, y2),
            max(origin_x, x2),
            max(origin_y, y2),
        ),
    }


def intersection_to_pixel_bounds(
    intersection: BaseGeometry, grid: GridInfo
) -> Optional[PixelBounds]:
    if intersection.is_empty:
        return None
    minx, miny, maxx, maxy = intersection.bounds
    col_min = max(0, math.floor((minx - grid["origin_x"]) / grid["pixel_w"]))
    col_max = min(grid["width"], math.ceil((maxx - grid["origin_x"]) / grid["pixel_w"]))
    row_min = max(0, math.floor((grid["origin_y"] - maxy) / grid["pixel_h"]))
    row_max = min(grid["height"], math.ceil((grid["origin_y"] - miny) / grid["pixel_h"]))
    if col_min >= col_max or row_min >= row_max:
        return None
    return int(row_min), int(row_max), int(col_min), int(col_max)


def align_window_to_chunk(
    pixel_bounds: PixelBounds, grid: GridInfo, chunk_size: int
) -> PixelBounds:
    row_min, row_max, col_min, col_max = pixel_bounds
    col0 = (col_min // chunk_size) * chunk_size
    row0 = (row_min // chunk_size) * chunk_size
    col1 = min(grid["width"], math.ceil(col_max / chunk_size) * chunk_size)
    row1 = min(grid["height"], math.ceil(row_max / chunk_size) * chunk_size)
    return row0, row1, col0, col1


def chunk_bbox(row: int, col: int, chunk_h: int, chunk_w: int, grid: GridInfo) -> Polygon:
    x1 = grid["origin_x"] + col * grid["x_scale"]
    x2 = grid["origin_x"] + (col + chunk_w) * grid["x_scale"]
    y1 = grid["origin_y"] + row * grid["y_scale"]
    y2 = grid["origin_y"] + (row + chunk_h) * grid["y_scale"]
    return box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def build_chunk_tasks(
    row0: int,
    row1: int,
    col0: int,
    col1: int,
    grid: GridInfo,
    intersection: BaseGeometry,
    chunk_size: int,
) -> list[ChunkTask]:
    tasks = []
    for row in range(row0, row1, chunk_size):
        for col in range(col0, col1, chunk_size):
            chunk_h = min(chunk_size, row1 - row)
            chunk_w = min(chunk_size, col1 - col)
            if chunk_bbox(row, col, chunk_h, chunk_w, grid).intersects(intersection):
                tasks.append((row, col, chunk_h, chunk_w))
    return tasks


def calculate_optimal_chunk_size(
    grid: GridInfo,
    pixel_bounds: PixelBounds,
    band_byte_sizes: Mapping[str, int],
    requested_chunk_size: Optional[int],
    request_byte_limit: int,
) -> int:
    total_bytes = max(1, sum(band_byte_sizes.values()))
    max_chunk = int(math.sqrt((request_byte_limit * 0.9) / total_bytes))
    max_chunk = max(DEFAULT_BLOCK_SIZE, (max_chunk // 64) * 64)
    if requested_chunk_size is not None:
        return max(1, min(requested_chunk_size, max_chunk))

    row_min, row_max, col_min, col_max = pixel_bounds
    bbox_height = row_max - row_min
    bbox_width = col_max - col_min
    bbox_max = max(bbox_height, bbox_width)
    if bbox_max <= DEFAULT_BLOCK_SIZE:
        return max(1, bbox_max)

    best = min(DEFAULT_BLOCK_SIZE, max_chunk)
    for candidate in range(DEFAULT_BLOCK_SIZE, max_chunk + 1, 64):
        if (row_min // candidate) == ((row_max - 1) // candidate) and (
            col_min // candidate
        ) == ((col_max - 1) // candidate):
            best = candidate
            break
        best = candidate
    return max(1, best)


def build_output_profile(
    grid: GridInfo,
    row0: int,
    col0: int,
    width: int,
    height: int,
    band_count: int,
    dtype_name: str,
    nodata: Union[float, int],
) -> dict[str, Any]:
    transform = Affine(
        grid["x_scale"],
        0.0,
        grid["origin_x"] + col0 * grid["x_scale"],
        0.0,
        grid["y_scale"],
        grid["origin_y"] + row0 * grid["y_scale"],
    )
    return {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": band_count,
        "dtype": dtype_name,
        "crs": grid["crs"],
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "tiled": True,
        "BIGTIFF": "IF_SAFER",
    }


def initialize_output_file(
    out_path: Path,
    profile: dict[str, Any],
    image_info: Mapping[str, Any],
    band_descriptions: Sequence[str],
    chunk_size: int,
    nodata: Union[float, int],
) -> rasterio.io.DatasetWriter:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dataset = rasterio.open(out_path, "w", **profile)
    dataset.descriptions = tuple(band_descriptions)
    dataset.update_tags(
        ee_id=str(image_info.get("id", "")),
        ee_version=str(image_info.get("version", "")),
    )
    if "properties" in image_info:
        dataset.update_tags(ee_properties_json=str(image_info["properties"]))

    fill_value = np.array(nodata, dtype=np.dtype(profile["dtype"])).item()
    for row in range(0, profile["height"], chunk_size):
        window_h = min(chunk_size, profile["height"] - row)
        for col in range(0, profile["width"], chunk_size):
            window_w = min(chunk_size, profile["width"] - col)
            dataset.write(
                np.full(
                    (profile["count"], window_h, window_w),
                    fill_value,
                    dtype=np.dtype(profile["dtype"]),
                ),
                window=Window(col, row, window_w, window_h),
            )
    return dataset
