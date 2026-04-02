# Python API

edown exposes three main functions and a set of configuration and result types.
All public symbols are available from the top-level `edown` package.

## Functions

### `search_images`

Discover images in an Earth Engine ImageCollection without downloading.

```python
from edown import AOI, SearchConfig, search_images

config = SearchConfig(
    collection_id="COPERNICUS/S2_SR_HARMONIZED",
    start_date="2024-06-01",
    end_date="2024-06-07",
    aoi=AOI.from_bbox((-0.15, 51.48, 0.02, 51.56)),
    bands=("B4", "B8"),
)
result = search_images(config)

print(f"Found {len(result.images)} images")
print(f"Alignment groups: {len(result.alignment_groups)}")
for image in result.images:
    print(f"  {image.image_id}  CRS={image.native_crs}")
```

::: edown.search_images
    options:
      show_source: false

### `download_images`

Search and download native-grid GeoTIFFs.

```python
from pathlib import Path
from edown import AOI, DownloadConfig, download_images

config = DownloadConfig(
    collection_id="COPERNICUS/S2_SR_HARMONIZED",
    start_date="2024-06-01",
    end_date="2024-06-07",
    aoi=AOI.from_bbox((-0.15, 51.48, 0.02, 51.56)),
    bands=("B4", "B8"),
    output_root=Path("data"),
    download_workers=10,
)
summary = download_images(config)

print(f"Downloaded: {summary.downloaded}")
print(f"Skipped:    {summary.skipped}")
print(f"Failed:     {summary.failed}")
print(f"Manifest:   {summary.manifest_path}")
```

::: edown.download_images
    options:
      show_source: false

### `stack_images`

Build Zarr stacks from a download manifest.

```python
from pathlib import Path
from edown import StackConfig, stack_images

config = StackConfig(
    manifest_path=Path("data/manifests/run-20240602T143022Z.json"),
    backend="threads",
)
results = stack_images(config)

for result in results:
    if result.output_path:
        print(f"Group {result.group_id}: {result.output_path}")
```

::: edown.stack_images
    options:
      show_source: false

---

## Configuration types

### `AOI`

Area of interest, constructed from a bounding box or GeoJSON file.

```python
from pathlib import Path
from edown import AOI

# From a bounding box (xmin, ymin, xmax, ymax) in WGS84
aoi = AOI.from_bbox((-0.15, 51.48, 0.02, 51.56))

# From a GeoJSON file
aoi = AOI.from_geojson(Path("my_area.geojson"))

# Access the bounds
print(aoi.bounds)  # (xmin, ymin, xmax, ymax)
```

::: edown.AOI
    options:
      show_source: false

### `SearchConfig`

Configuration for `search_images`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `collection_id` | `str` | required | Earth Engine ImageCollection ID |
| `start_date` | `str` | required | Start date `YYYY-MM-DD` (inclusive) |
| `end_date` | `str` | required | End date `YYYY-MM-DD` (inclusive) |
| `aoi` | `AOI` | required | Area of interest |
| `bands` | `tuple[str, ...]` | `()` | Explicit band IDs to select |
| `band_include` | `tuple[str, ...]` | `()` | Regex include filters |
| `band_exclude` | `tuple[str, ...]` | `()` | Regex exclude filters |
| `rename_map` | `dict[str, str]` | `{}` | Band renaming map |
| `scale_map` | `dict[str, float]` | `{}` | Band scaling factors |
| `transform_plugin` | `str` or `None` | `None` | Plugin as `module:function` |
| `server_url` | `str` | high-volume URL | Earth Engine API endpoint |

### `DownloadConfig`

Extends `SearchConfig` with download-specific options.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_root` | `Path` | `data` | Root output directory |
| `manifest_path` | `Path` or `None` | auto | Manifest output path |
| `chunk_size` | `int` or `None` | auto | Chunk size in pixels |
| `chunk_size_mode` | `str` | `"auto"` | `"auto"` or `"fixed"` |
| `prepare_workers` | `int` | 10 | Job preparation threads |
| `download_workers` | `int` | 10 | Download threads |
| `max_inflight_chunks` | `int` | 32 | Max concurrent chunk requests |
| `max_retries` | `int` | 4 | Retries per chunk |
| `retry_delay_seconds` | `float` | 2.0 | Initial backoff delay |
| `request_byte_limit` | `int` | 48 MB | Max bytes per request |
| `overwrite` | `bool` | `False` | Replace existing outputs |
| `resume` | `bool` | `True` | Skip existing outputs |
| `nodata` | `float` or `None` | auto | Nodata fill value |

### `StackConfig`

Configuration for `stack_images`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `manifest_path` | `Path` | required | Path to download manifest |
| `output_root` | `Path` or `None` | from manifest | Override output root |
| `backend` | `str` | `"threads"` | `"threads"`, `"dask-local"`, or `"dask-slurm"` |
| `overwrite` | `bool` | `False` | Replace existing Zarr stores |
| `n_workers` | `int` | 4 | Dask worker count |
| `cores_per_worker` | `int` | 1 | Cores per Dask worker |
| `memory_per_worker` | `str` | `"1GB"` | Memory per Dask worker |
| `slurm_queue` | `str` or `None` | `None` | SLURM partition |
| `slurm_account` | `str` or `None` | `None` | SLURM account |

---

## Result types

### `SearchResult`

Returned by `search_images`.

| Property | Type | Description |
|----------|------|-------------|
| `collection_id` | `str` | Collection queried |
| `images` | `tuple[ImageRecord, ...]` | Discovered images |
| `alignment_groups` | `tuple[AlignmentGroup, ...]` | Grid-compatible groups |
| `selected_band_ids` | `tuple[str, ...]` | Band IDs selected |
| `output_band_names` | `tuple[str, ...]` | Output names (after renaming) |

### `ImageRecord`

Metadata for a single discovered image.

| Property | Type | Description |
|----------|------|-------------|
| `image_id` | `str` | Earth Engine image ID |
| `acquisition_time_utc` | `datetime` | Acquisition time (UTC) |
| `native_crs` | `str` | Native CRS code |
| `native_transform` | `tuple[float, ...]` | Affine transform |
| `native_width` / `native_height` | `int` | Image dimensions |
| `alignment_signature` | `str` | 12-char group signature |
| `selected_band_ids` | `tuple[str, ...]` | Selected bands |
| `output_dtype` | `str` | NumPy dtype name |

### `AlignmentGroup`

A group of images that share the same grid.

| Property | Type | Description |
|----------|------|-------------|
| `group_id` | `str` | Alignment signature |
| `image_ids` | `tuple[str, ...]` | Images in the group |
| `crs` | `str` | Shared CRS |
| `band_names` | `tuple[str, ...]` | Band names |
| `dtype` | `str` | Output dtype |

### `DownloadSummary`

Returned by `download_images`.

| Property | Type | Description |
|----------|------|-------------|
| `manifest_path` | `Path` | Path to the written manifest |
| `results` | `tuple[DownloadResult, ...]` | Per-image results |
| `downloaded` | `int` | Count of successfully downloaded images |
| `skipped` | `int` | Count of skipped images |
| `failed` | `int` | Count of failed images |

### `DownloadResult`

Per-image download outcome.

| Property | Type | Description |
|----------|------|-------------|
| `image_id` | `str` | Earth Engine image ID |
| `status` | `str` | `downloaded`, `skipped_*`, or `failed` |
| `tiff_path` | `Path` or `None` | Output GeoTIFF path |
| `chunk_count` | `int` | Chunks processed |
| `error` | `str` or `None` | Error message if failed |

### `StackResult`

Per-group stacking outcome.

| Property | Type | Description |
|----------|------|-------------|
| `group_id` | `str` | Alignment signature |
| `image_count` | `int` | Images in the stack |
| `output_path` | `Path` or `None` | Zarr store path |
| `skipped_reason` | `str` or `None` | Why the group was skipped |
