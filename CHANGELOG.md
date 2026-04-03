# Changelog

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
