# Changelog

## 0.2.2

- `SearchConfig.image_ids` / `--image-id` restrict a search to specific images.
  The filter is applied server-side via `ee.Filter.inList` on `system:index`, so
  counts, recursive date splitting and metadata transfer all shrink with the
  selection rather than fetching a whole window to discard most of it. Ids may
  be bare `system:index` values or full asset ids; ids matching nothing are
  logged rather than silently dropped.

## Unreleased

- Support MODIS/VIIRS and other collections that Earth Engine reports with
  legacy `SR-ORG` CRS codes (e.g. `SR-ORG:6974` for MODIS sinusoidal). These
  codes are not resolvable by PROJ, which previously failed every download with
  `Preparation failed: Invalid projection`. The new `edown.crs.proj_crs_for`
  helper maps them to an equivalent proj4 definition at the PROJ/rasterio
  boundaries (AOI geometry transform and output GeoTIFF tagging) while the Earth
  Engine pixel request keeps the original EE code.

## 0.2.1

- Finalize each image immediately after its last chunk downloads instead of
  waiting for all images to complete. Metadata sidecars are written and datasets
  closed per-image, so interrupted runs resume correctly without re-downloading
  completed images.

## 0.2.0

- Fix thread-safety issue: add per-dataset write lock for concurrent GeoTIFF chunk writes.
- Align CLI default values with constants module (prepare-workers, download-workers).
- Use portable JSON-based alignment signature hashing instead of Python `repr()`.
- Improve stack performance with O(1) image lookup instead of O(n) scan per group.
- Rewrite documentation: expanded getting-started guide, full CLI reference with
  option tables, concepts page covering native grids, alignment groups, chunking,
  output layout, authentication, and transform plugins, manifest format reference
  with examples, and comprehensive Python API docs with usage examples for all
  public types.

## 0.1.1

- Add verified Python 3.13 and 3.14 support in package metadata, CI, docs, and release workflows.
- Keep build artifacts and local workspace directories out of Hatch packages.

## 0.1.0

- Initial package scaffold for `edown`.
- Native-grid Google Earth Engine GeoTIFF downloader with run manifest generation.
- Optional Zarr stacking for grid-compatible image groups.
- CLI, tests, documentation, and GitHub Actions release pipeline.
