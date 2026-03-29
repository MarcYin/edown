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

`edown` supports Python 3.9 through 3.14.

For local development:

```bash
python -m pip install -e ".[dev,stack,dask]"
```

## Authentication

`edown` prefers Earth Engine service-account credentials when both of these environment variables are set:

- `GEE_SERVICE_ACCOUNT`
- `GEE_SERVICE_ACCOUNT_KEY`

Otherwise it tries, in order:

- persistent Earth Engine user credentials
- Google application default credentials

If both user-auth and ADC refresh tokens are stale, reauthenticate before running downloads.

## CLI

Search only:

```bash
edown search \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B4 \
  --band B8 \
  --manifest-path manifests/search.json
```

Download native-grid GeoTIFFs:

```bash
edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --geojson docs/examples/aoi.geojson \
  --band B4 \
  --band B8 \
  --output-root ./data
```

Build Zarr stacks from compatible groups:

```bash
edown stack \
  --manifest-path manifests/run.json \
  --output-root ./data
```

Run the bundled end-to-end Sentinel-2 example:

```bash
python examples/s2_find_download_stack.py --output-root ./data/live-s2
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
    bands=("B4", "B8"),
    output_root=Path("data"),
)

summary = download_images(config)
print(summary.manifest_path)
```

## Live Integration Test

The default test suite is mocked and offline. For a real end-to-end Sentinel-2 smoke test, install the stack extras:

```bash
python -m pip install -e ".[dev,stack]"
```

Then run:

```bash
export EDOWN_RUN_LIVE_TESTS=1
python -m pytest -s tests/test_live_s2.py
```

Default live settings:

- collection: `COPERNICUS/S2_SR_HARMONIZED`
- dates: `2024-06-01` through `2024-06-03`
- bbox: `-0.1278,51.5072,-0.1270,51.5078`
- bands: `B4,B8`

You can override them with:

- `EDOWN_LIVE_COLLECTION_ID`
- `EDOWN_LIVE_START_DATE`
- `EDOWN_LIVE_END_DATE`
- `EDOWN_LIVE_BBOX`
- `EDOWN_LIVE_BANDS`

This requires valid Earth Engine authentication, via either:

- `GEE_SERVICE_ACCOUNT` and `GEE_SERVICE_ACCOUNT_KEY` (path to a service-account JSON key file)
- existing local Earth Engine credentials
- valid Google application default credentials

## Notes

- `--chunk-size` is only used as an exact size when `--chunk-size-mode fixed` is set.
- In the default `auto` mode, `edown` estimates chunk sizes per image from the AOI window and request byte limits.

## Development

- `python -m pytest`
- `ruff check .`
- `mypy src`
- `python -m build`

Docs are built with MkDocs Material and published to GitHub Pages from GitHub Actions.
