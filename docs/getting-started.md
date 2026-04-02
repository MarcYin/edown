# Getting Started

## Install

```bash
pip install edown
```

edown supports Python 3.9 through 3.14.

To include Zarr stacking support:

```bash
pip install "edown[stack]"
```

For development (linting, type checking, tests, and stacking):

```bash
pip install -e ".[dev,stack,dask]"
```

## Authenticate

edown needs access to Google Earth Engine.  Set up one of:

**Option 1 -- Service account** (recommended for CI and servers):

```bash
export GEE_SERVICE_ACCOUNT="my-sa@my-project.iam.gserviceaccount.com"
export GEE_SERVICE_ACCOUNT_KEY="/path/to/key.json"
```

**Option 2 -- Local credentials** (simplest for personal use):

```bash
earthengine authenticate
```

**Option 3 -- Application Default Credentials**:

```bash
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/earthengine
```

edown tries each strategy in order and uses the first one that succeeds.

## Your first download

Search and download Sentinel-2 bands B4 (red) and B8 (NIR) over London:

```bash
edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B4 --band B8 \
  --output-root ./data
```

This will:

1. Query Earth Engine for matching images
2. Download each image as a native-grid GeoTIFF under `./data/images/`
3. Write a run manifest under `./data/manifests/`

## Build a Zarr stack

Once the download completes, stack alignment-compatible images into a Zarr
datacube:

```bash
edown stack \
  --manifest-path ./data/manifests/run-*.json \
  --output-root ./data
```

The output Zarr stores appear under `./data/stacks/`, one per alignment group,
with dimensions `(time, band, y, x)`.

## Python API

The same workflow from Python:

```python
from pathlib import Path
from edown import (
    AOI,
    DownloadConfig,
    StackConfig,
    download_images,
    stack_images,
)

# Download
config = DownloadConfig(
    collection_id="COPERNICUS/S2_SR_HARMONIZED",
    start_date="2024-06-01",
    end_date="2024-06-07",
    aoi=AOI.from_bbox((-0.15, 51.48, 0.02, 51.56)),
    bands=("B4", "B8"),
    output_root=Path("data"),
)
summary = download_images(config)
print(f"{summary.downloaded} images downloaded")

# Stack
stack_config = StackConfig(manifest_path=summary.manifest_path)
results = stack_images(stack_config)
for result in results:
    if result.output_path:
        print(f"Stack: {result.output_path}")
```

## Using a GeoJSON AOI

Instead of a bounding box, pass a GeoJSON file:

```bash
edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --geojson my_area.geojson \
  --band B4 --band B8 \
  --output-root ./data
```

edown accepts GeoJSON `Feature`, `Geometry`, or `FeatureCollection` files.
For a `FeatureCollection`, all geometries are merged into a single AOI.

## Tuning performance

A few options to control download speed:

| Option | Default | Purpose |
|--------|---------|---------|
| `--download-workers` | 10 | Number of parallel download threads |
| `--prepare-workers` | 10 | Threads for job preparation (CRS transforms) |
| `--max-inflight-chunks` | 32 | Cap on in-flight chunk requests |
| `--request-byte-limit` | 48 MB | Max bytes per chunk request |
| `--max-retries` | 4 | Retries per chunk with exponential backoff |

## Live smoke test

Run a real end-to-end test against Earth Engine:

```bash
pip install -e ".[dev,stack]"
export EDOWN_RUN_LIVE_TESTS=1
python -m pytest -s tests/test_live_s2.py
```

Override defaults with environment variables: `EDOWN_LIVE_COLLECTION_ID`,
`EDOWN_LIVE_START_DATE`, `EDOWN_LIVE_END_DATE`, `EDOWN_LIVE_BBOX`,
`EDOWN_LIVE_BANDS`.
