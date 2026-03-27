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
  - `GEE_SERVICE_ACCOUNT_KEY`
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
  --band B04 \
  --band B08 \
  --output-root ./data
```

If you want an exact chunk size, add `--chunk-size-mode fixed --chunk-size 512`.
