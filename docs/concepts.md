# Concepts

## Native grid preservation

Every satellite image in Earth Engine has a **native grid** defined by its CRS,
affine transform, and pixel dimensions.  When you force all images into a
common projection you introduce resampling artifacts.  edown avoids this by
downloading every image in its original grid.

## Alignment groups

Images that share the same CRS, transform, dimensions, bands, and output dtype
have the same **alignment signature** (a 12-character SHA-1 prefix of those
properties).  edown groups these images together so that Zarr stacking can
combine them without reprojection.

For example, a week of Sentinel-2 downloads over London might produce:

| Group | CRS | Images |
|-------|-----|--------|
| `a3f8c10b2e47` | EPSG:32630 (UTM 30N) | 5 |
| `e91d04fa83c2` | EPSG:32631 (UTM 31N) | 2 |

Each group becomes one Zarr store with dimensions `(time, band, y, x)`.

## Chunking

Large images are split into rectangular **chunks** for download.  edown
estimates an optimal chunk size per image based on:

- the number and byte size of selected bands
- a configurable request byte limit (default 48 MB)
- 64-pixel alignment for efficient tiling

In `auto` mode (the default), edown picks the smallest chunk size that covers
the AOI intersection in a single chunk when possible, and falls back to the
largest size that fits the byte limit otherwise.

Set `--chunk-size-mode fixed --chunk-size 512` to override with an exact size.

## Output layout

```
output_root/
├── manifests/
│   └── run-20240602T143022Z.json
├── images/
│   └── COPERNICUS_S2_SR_HARMONIZED/
│       ├── 20240601T101031_T32UQD.tif
│       ├── 20240601T101031_T32UQD.tif.metadata.json
│       └── ...
└── stacks/
    └── COPERNICUS_S2_SR_HARMONIZED/
        └── a3f8c10b2e47.zarr/
```

- **images/**: one GeoTIFF per image, plus a `.metadata.json` sidecar with the
  raw Earth Engine image properties.
- **stacks/**: one Zarr store per alignment group, created by `edown stack`.
- **manifests/**: JSON manifest that ties everything together.

## Resume and overwrite

By default, `edown download` runs in **resume** mode: if a GeoTIFF and its
metadata sidecar already exist, the image is skipped.  This makes it safe to
re-run after a partial failure.

Pass `--overwrite` to re-download and replace existing files.  When both
`--resume` and `--overwrite` are set, overwrite takes precedence.

## Authentication

edown tries three authentication strategies in order:

1. **Service account** -- when `GEE_SERVICE_ACCOUNT` and
   `GEE_SERVICE_ACCOUNT_KEY` environment variables are set.
2. **Persistent credentials** -- the local Earth Engine credential store
   (created by `earthengine authenticate`).
3. **Application Default Credentials (ADC)** -- Google Cloud ADC with the
   Earth Engine scope.

The first strategy that succeeds is used.  If all three fail, edown raises an
`AuthenticationError` with details from each attempt.

## Transform plugins

A transform plugin is a Python function that receives the `ee.Image`, the raw
image info dict, and the download config, and returns a modified `ee.Image`.
Specify it as `module:function`:

```bash
edown download ... --transform-plugin mypackage.transforms:cloud_mask
```

```python
def cloud_mask(ee_image, image_info, config):
    qa = ee_image.select("QA60")
    mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return ee_image.updateMask(mask)
```

When a transform plugin or scale map is active, the output dtype is promoted to
`float32` to accommodate the transformation.
