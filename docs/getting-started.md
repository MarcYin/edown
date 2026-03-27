# Getting Started

## Install

```bash
python -m pip install edown
```

Development install:

```bash
python -m pip install -e ".[dev,stack,dask]"
```

## Authenticate

Use either:

- service account environment variables:
  - `GEE_SERVICE_ACCOUNT`
  - `GEE_SERVICE_ACCOUNT_KEY` pointing to a service-account JSON key file
- or the standard Earth Engine local authentication flow already configured on the machine
- or Google application default credentials if they are valid for Earth Engine

If local credentials have expired, refresh them before testing downloads.

## Download Example

```bash
edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B4 \
  --band B8 \
  --output-root ./data
```

If you want an exact chunk size, add `--chunk-size-mode fixed --chunk-size 512`.

## Live Sentinel-2 Smoke Test

For a real search, download, and stack run against Earth Engine:

```bash
python -m pip install -e ".[dev,stack]"
export EDOWN_RUN_LIVE_TESTS=1
python -m pytest -s tests/test_live_s2.py
```

Default live settings:

- collection: `COPERNICUS/S2_SR_HARMONIZED`
- dates: `2024-06-01` through `2024-06-03`
- bbox: `-0.1278,51.5072,-0.1270,51.5078`
- bands: `B4,B8`

Override them with:

- `EDOWN_LIVE_COLLECTION_ID`
- `EDOWN_LIVE_START_DATE`
- `EDOWN_LIVE_END_DATE`
- `EDOWN_LIVE_BBOX`
- `EDOWN_LIVE_BANDS`
