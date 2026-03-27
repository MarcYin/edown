# edown

`edown` is a Google Earth Engine downloader that discovers images for a location and time range, downloads each image in its native grid as GeoTIFF, and can optionally build Zarr stacks for grid-compatible groups.

## What It Does

- Searches an ImageCollection by date range and AOI.
- Preserves each image's native CRS and transform instead of forcing a common projection.
- Downloads intersecting chunks in parallel across multiple images.
- Writes a run manifest with discovery, download, and stack metadata.
- Builds Zarr outputs only when images share an alignment signature.

## Installation

```bash
python -m pip install edown
```

For local development:

```bash
python -m pip install -e ".[dev,stack,dask]"
```

## Authentication

`edown` prefers Earth Engine service-account credentials when both of these environment variables are set:

- `GEE_SERVICE_ACCOUNT`
- `GEE_SERVICE_ACCOUNT_KEY`

Otherwise it falls back to the default Earth Engine user/application-default authentication flow.

## CLI

Search only:

```bash
edown search \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B04 \
  --band B08 \
  --manifest-path manifests/search.json
```

Download native-grid GeoTIFFs:

```bash
edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --geojson docs/examples/aoi.geojson \
  --band B04 \
  --band B08 \
  --output-root ./data
```

Build Zarr stacks from compatible groups:

```bash
edown stack \
  --manifest-path manifests/run.json \
  --output-root ./data
```

## Python API

```python
from pathlib import Path

from edown import AOI, DownloadConfig, download_images

config = DownloadConfig(
    collection_id="COPERNICUS/S2_SR_HARMONIZED",
    start_date="2024-06-01",
    end_date="2024-06-07",
    aoi=AOI.from_bbox((-0.15, 51.48, 0.02, 51.56)),
    bands=("B04", "B08"),
    output_root=Path("data"),
)

summary = download_images(config)
print(summary.manifest_path)
```

## Notes

- `--chunk-size` is only used as an exact size when `--chunk-size-mode fixed` is set.
- In the default `auto` mode, `edown` estimates chunk sizes per image from the AOI window and request byte limits.

## Development

- `python -m pytest`
- `ruff check .`
- `mypy src`
- `python -m build`

Docs are built with MkDocs Material and published to GitHub Pages from GitHub Actions.
