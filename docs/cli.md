# CLI Reference

edown provides three commands that mirror the search-download-stack workflow.
All commands support `--help` for the full option set.

## `edown search`

Discover matching images and write a manifest without downloading any data.

```bash
edown search \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B4 --band B8 \
  --manifest-path manifests/search.json
```

### Common options

| Option | Required | Description |
|--------|----------|-------------|
| `--collection-id` | Yes | Earth Engine ImageCollection ID |
| `--start-date` | Yes | Inclusive start date (`YYYY-MM-DD`) |
| `--end-date` | Yes | Inclusive end date (`YYYY-MM-DD`) |
| `--bbox` | One of bbox/geojson | AOI bounding box: `xmin ymin xmax ymax` (WGS84) |
| `--geojson` | One of bbox/geojson | Path to a GeoJSON file for the AOI |
| `--band` | No | Band ID to request (repeatable, or comma-separated) |
| `--band-include` | No | Regex include filter for auto-discovered bands |
| `--band-exclude` | No | Regex exclude filter for auto-discovered bands |
| `--rename-map` | No | JSON object for band renaming, e.g. `'{"B4": "red"}'` |
| `--scale-map` | No | JSON object for band scaling, e.g. `'{"B4": 0.0001}'` |
| `--transform-plugin` | No | Plugin in `module:function` format |
| `--server-url` | No | Earth Engine API URL (default: high-volume endpoint) |
| `--manifest-path` | No | Output manifest path (auto-generated if omitted) |

### Band selection

If `--band` is provided, only those bands are selected (with alias resolution:
`B4` matches `B04`).  Otherwise, all bands are included unless filtered by
`--band-include` and `--band-exclude` regex patterns.

---

## `edown download`

Run discovery and download native-grid GeoTIFFs in parallel.  Accepts all
search options above, plus:

```bash
edown download \
  --collection-id COPERNICUS/S2_SR_HARMONIZED \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --bbox -0.15 51.48 0.02 51.56 \
  --band B4 --band B8 \
  --output-root ./data \
  --download-workers 10
```

### Download options

| Option | Default | Description |
|--------|---------|-------------|
| `--output-root` | `data` | Root directory for outputs |
| `--manifest-path` | auto | Path for the run manifest |
| `--chunk-size` | auto | Chunk size in pixels |
| `--chunk-size-mode` | `auto` | `auto` or `fixed` |
| `--prepare-workers` | 10 | Parallel threads for job preparation |
| `--download-workers` | 10 | Parallel threads for chunk downloads |
| `--max-inflight-chunks` | 32 | Maximum concurrent chunk requests |
| `--max-retries` | 4 | Retries per failed chunk |
| `--retry-delay-seconds` | 2.0 | Initial retry backoff (doubles each attempt) |
| `--request-byte-limit` | 48 MB | Maximum bytes per chunk request |
| `--nodata` | auto | Nodata value (default: NaN for float, max for int) |
| `--overwrite / --no-overwrite` | off | Replace existing files |
| `--resume / --no-resume` | on | Skip images that already have output files |

### Output structure

```
output_root/
├── manifests/
│   └── run-20240602T143022Z.json
└── images/
    └── COPERNICUS_S2_SR_HARMONIZED/
        ├── 20240601T101031_T32UQD.tif
        └── 20240601T101031_T32UQD.tif.metadata.json
```

---

## `edown stack`

Read a manifest and build one Zarr store per alignment group.

```bash
edown stack \
  --manifest-path ./data/manifests/run-20240602T143022Z.json \
  --output-root ./data \
  --backend dask-local \
  --n-workers 4
```

### Stack options

| Option | Default | Description |
|--------|---------|-------------|
| `--manifest-path` | **required** | Path to a download manifest |
| `--output-root` | from manifest | Override the output root |
| `--backend` | `threads` | `threads`, `dask-local`, or `dask-slurm` |
| `--overwrite / --no-overwrite` | off | Replace existing Zarr stores |
| `--n-workers` | 4 | Number of Dask workers |
| `--cores-per-worker` | 1 | Cores per Dask worker |
| `--memory-per-worker` | `1GB` | Memory per Dask worker |
| `--slurm-queue` | none | SLURM partition (dask-slurm only) |
| `--slurm-account` | none | SLURM account (dask-slurm only) |

### Backends

- **threads** -- reads TIFFs sequentially in the main process.  No extra
  dependencies.  Good for small runs.
- **dask-local** -- spins up a `LocalCluster` with configurable workers.
  Requires `pip install "edown[stack,dask]"`.
- **dask-slurm** -- submits jobs to a SLURM cluster via `dask-jobqueue`.
  Requires `pip install "edown[stack,dask]"`.

---

## Global options

| Option | Description |
|--------|-------------|
| `--verbose` | Enable debug logging (before the subcommand) |
| `--help` | Show help for any command |

```bash
edown --verbose download --help
```
