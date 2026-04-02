# edown

**Native-grid Google Earth Engine downloader with alignment-aware Zarr stacking.**

edown discovers satellite images for a location and time range, downloads each
image in its own native CRS and pixel grid as a GeoTIFF, and optionally builds
Zarr stacks for groups of images that share the same grid.

## Why native grid?

Most Earth Engine download tools reproject every image into a single common
grid.  This is convenient but introduces resampling artifacts and discards the
original pixel alignment.  edown takes a different approach: it preserves the
grid that each image was acquired on, and only stacks images together when they
are already aligned.

## Key features

| Feature | Description |
|---------|-------------|
| **Search** | Filter an `ImageCollection` by date range and area of interest |
| **Download** | Parallel, chunked GeoTIFF downloads with automatic retry and resume |
| **Stack** | Build Zarr datacubes from alignment-compatible image groups |
| **Manifest** | Machine-readable JSON log of every run for reproducibility |
| **Band aliasing** | Request `B4` and edown resolves it to `B04` automatically |
| **Transform plugins** | Apply custom band math or masking before download |
| **Progress UI** | Rich terminal display with per-chunk grid visualization |

## Quick start

```bash
pip install edown

edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B4 --band B8 \
  --output-root ./data
```

Or from Python:

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
print(f"{summary.downloaded} downloaded, {summary.failed} failed")
```

## How it works

```
                      search
  ImageCollection ──────────────► ImageRecords
                                      │
                                      │ group by alignment signature
                                      ▼
                                AlignmentGroups
                                      │
                         download     │     stack
                    ┌─────────────────┤──────────────────┐
                    ▼                 ▼                   ▼
              image_A.tif      image_B.tif         group.zarr
              image_A.tif.     image_B.tif.
              metadata.json    metadata.json
```

1. **Search** queries Earth Engine and groups images by their alignment
   signature (a hash of CRS, transform, dimensions, bands, and dtype).
2. **Download** fetches each image in parallel chunks, writing native-grid
   GeoTIFFs with nodata fill for pixels outside the AOI.
3. **Stack** reads the manifest and builds one Zarr store per alignment group,
   with `(time, band, y, x)` dimensions.

See [Concepts](concepts.md) for details on alignment groups, chunking, and
the output layout.
