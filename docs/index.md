# edown

`edown` is a Google Earth Engine downloader focused on a simple rule: keep every image in its own native grid unless there is a safe reason to stack aligned outputs together.

Use it to:

- search an ImageCollection by location and time range
- download each intersecting image as a native-grid GeoTIFF
- persist a machine-readable manifest for the run
- build Zarr stacks only for alignment-compatible groups

The package exposes both a Python API and a `click`-based CLI.
