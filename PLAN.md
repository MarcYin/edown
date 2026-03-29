# Edown Bootstrap And Release Plan

## Summary
- Bootstrap `/Users/fengyin/Documents/edown` into a git repo, add `origin` as `git@github.com:MarcYin/edown.git`, use `main` as the default branch, and push the initial scaffold to the empty GitHub repository.
- Build `edown` as a `src`-layout Python package that combines the useful logic from the two current scripts, but does not commit those scripts to the repository.
- Make GeoTIFF the primary output: one file per discovered image, clipped to the AOI in that image’s native CRS/grid.
- Add an optional stacking stage that creates Zarr outputs only for grid-compatible images; mixed-CRS or mixed-transform collections are split into separate alignment groups instead of being forced into one CRS.
- First implementation artifact: add `PLAN.md` at repo root containing this plan, then scaffold `src/edown/`, tests, docs, and `.github/workflows/`.

## Repository And Packaging
- Initialize local git in `/Users/fengyin/Documents/edown`, set remote `origin` to `git@github.com:MarcYin/edown.git`, create branch `main`, and use that as the default branch.
- Add `.gitignore` before the first commit and explicitly ignore:
  - `gee_downloader.py`
  - `access_GEE_generic.py`
- Treat those two scripts as local reference material only: read from them during implementation, extract/rewrite the needed logic into package modules, but do not track or publish the original files.
- Use `src` layout with distribution/import name `edown`.
- Python support: `>=3.9,<3.15`.
- Build backend: `hatchling`.
- Standard project files: `README.md`, `LICENSE` (MIT), `CHANGELOG.md`, `pyproject.toml`, `.gitignore`, docs config, test config, and contributor docs.

## Public APIs And CLI
- Public Python API:
  - `search_images(config: SearchConfig) -> SearchResult`
  - `download_images(config: DownloadConfig) -> DownloadSummary`
  - `stack_images(config: StackConfig) -> list[StackResult]`
- Public types:
  - `AOI` with `bbox` or `geojson_path`
  - `SearchConfig` for collection, time range, AOI, band selection, rename/scale, and auth/server settings
  - `DownloadConfig` for search config plus output root, worker counts, retry policy, chunk size mode, resume/overwrite, and manifest path
  - `StackConfig` for manifest/input source, backend (`threads`, `dask-local`, `dask-slurm`), and output root
  - `ImageRecord`, `DownloadResult`, `DownloadSummary`, `AlignmentGroup`, and `StackResult`
- CLI commands:
  - `edown search ...` discovers images and writes a manifest without downloading
  - `edown download ...` performs search plus native-grid GeoTIFF download
  - `edown stack ...` builds one Zarr store per compatible alignment group from a manifest or download directory
- AOI input:
  - support `--bbox xmin ymin xmax ymax`
  - support `--geojson path`
  - GeoJSON is used for AOI geometry/bounds in discovery and clipping logic; v1 does not do polygon-mask rasterization
- Authentication:
  - auto mode uses `GEE_SERVICE_ACCOUNT` and `GEE_SERVICE_ACCOUNT_KEY` when both exist
  - otherwise fall back to normal Earth Engine user/application-default auth
  - default endpoint is the high-volume Earth Engine URL, with override support
- Keep band rename/scale behavior, but replace raw `mask_eval` with a safer plugin hook: Python callable API and CLI `--transform-plugin module:function`

## Implementation Changes
- Split the current script logic into focused modules for auth, config/models, discovery, projection/grid math, chunk planning, downloader, manifest I/O, stacking, CLI, and errors.
- Reuse the generic script’s discovery features:
  - temporal chunking around the 5000-image limit
  - band selection and include/exclude regex filters
  - rename/scale mapping
  - request-size-based chunk estimation
- Reuse the downloader script’s native-grid strategy:
  - compute AOI intersection in each image’s own CRS
  - plan chunks only for intersecting windows
  - fetch chunks in parallel across many images
- Replace the current “submit everything at once” behavior with a bounded global task queue so large runs stay memory-safe.
- Write GeoTIFFs from the coordinator thread; worker threads only fetch chunk data.
- Record each image’s native CRS, affine transform, dimensions, selected bands, and alignment signature in the manifest.
- Define stack compatibility as matching CRS, affine transform, AOI window shape, output band order, and dtype.
- Build one Zarr store per alignment group; incompatible groups are skipped with explicit manifest/report entries.
- Keep Dask local and SLURM as optional extras and optional backends, not core requirements.
- Standardize output layout:
  - `manifests/run-<timestamp>.json`
  - `images/<collection>/<safe-image-id>.tif`
  - `images/<collection>/<safe-image-id>.tif.metadata.json`
  - `stacks/<collection>/<alignment-group>.zarr`

## CI, Docs, And Release
- Dependencies:
  - base: `earthengine-api`, `numpy`, `rasterio`, `shapely`, `pyproj`, `click`, `tenacity`
  - stack extra: `xarray`, `zarr`, `dask[array]`
  - dask extra: `distributed`, `dask_jobqueue`, `tqdm`
  - dev/docs: `pytest`, `pytest-mock`, `ruff`, `mypy`, `mkdocs-material`, `mkdocstrings[python]`
- GitHub Actions workflows:
  - `ci.yml` for Ruff, mypy, unit tests, and mocked integration tests on Python 3.9, 3.10, 3.11, 3.12, 3.13, and 3.14
  - `build.yml` for wheel/sdist build plus `twine check`
  - `docs.yml` for MkDocs build on PRs and deploy to GitHub Pages on `main`
  - `publish.yml` for PyPI release on tags like `v0.1.0`
  - `smoke-live-gee.yml` as an optional `workflow_dispatch` live smoke test using repo secrets
- Docs stack:
  - MkDocs Material with `mkdocstrings`
  - publish to GitHub Pages at `https://marcyin.github.io/edown/`
  - include install, auth, quickstart, CLI reference, Python API reference, manifest format, and mixed-grid stacking behavior
- Publishing:
  - configure PyPI Trusted Publishing from GitHub Actions with `id-token: write`
  - publish on version tags from `main`

## Test Plan
- Unit tests:
  - AOI parsing for bbox and GeoJSON
  - collection discovery chunking around the 5000-image threshold
  - band selection, rename, scale, and missing-band handling
  - native-grid AOI intersection and chunk window planning
  - chunk-size estimation against request-size limits
  - alignment-signature grouping for stack compatibility
  - manifest serialization plus resume/overwrite behavior
- Mocked integration tests:
  - threaded multi-image download writes valid GeoTIFFs and metadata sidecars
  - mixed-grid collections download successfully and split into separate alignment groups
  - stack creation succeeds for compatible groups and skips incompatible ones cleanly
  - retry and partial-failure cases are surfaced correctly in the manifest and CLI exit code
  - transform plugin modifies server-side image preparation without unsafe eval
- Release validation:
  - wheel and sdist build cleanly
  - docs build without broken references
  - optional live smoke workflow downloads a tiny public AOI and verifies outputs

## Assumptions And Defaults
- `edown` remains the package/distribution name unless PyPI availability changes before first release.
- GeoTIFF is the main artifact; Zarr is derived and only built for compatible native-grid groups.
- No automatic reprojection or “single common CRS” behavior is allowed in the default workflow.
- `click` remains the CLI framework.
- The two current scripts are intentionally excluded from git via `.gitignore` and are not part of the published package.
