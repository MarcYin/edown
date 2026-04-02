# Manifest

Every edown run writes a JSON manifest that captures the full state of the
search, download, and (optionally) stack phases.  This makes runs reproducible
and allows downstream tools to inspect results programmatically.

## Location

Manifests are written to `<output_root>/manifests/run-<timestamp>.json` by
default.  Override with `--manifest-path`.

## Structure

```json
{
  "schema_version": 1,
  "config": { ... },
  "search": {
    "collection_id": "COPERNICUS/S2_SR_HARMONIZED",
    "start_date": "2024-06-01",
    "end_date": "2024-06-07",
    "aoi_bounds": [-0.15, 51.48, 0.02, 51.56],
    "selected_band_ids": ["B04", "B08"],
    "output_band_names": ["B04", "B08"],
    "images": [ ... ],
    "alignment_groups": [ ... ],
    "created_at": "2024-06-02T14:30:22+00:00"
  },
  "download": {
    "manifest_path": "data/manifests/run-20240602T143022Z.json",
    "output_root": "data",
    "results": [ ... ],
    "created_at": "2024-06-02T14:35:10+00:00"
  },
  "stack": [ ... ],
  "stack_config": { ... }
}
```

## Sections

### `config`

The effective `DownloadConfig` (or `SearchConfig`) serialized as JSON.  This
records every parameter so the run can be reproduced.

### `search`

Discovery results including:

- **images** -- one entry per discovered image with native CRS, transform,
  dimensions, selected bands, output dtype, and the alignment signature.
- **alignment_groups** -- groups of image IDs that share the same grid, ready
  for stacking.

### `download`

One result per image:

| Field | Description |
|-------|-------------|
| `image_id` | Earth Engine image ID |
| `status` | `downloaded`, `skipped_existing`, `skipped_outside_aoi`, `skipped_missing_bands`, or `failed` |
| `tiff_path` | Absolute path to the output GeoTIFF |
| `metadata_path` | Path to the `.metadata.json` sidecar |
| `chunk_count` | Number of chunks downloaded |
| `error` | Error message (failed images only) |

### `stack`

Added by `edown stack`.  One result per alignment group:

| Field | Description |
|-------|-------------|
| `group_id` | Alignment signature |
| `image_count` | Number of images in the stack |
| `output_path` | Path to the Zarr store |
| `skipped_reason` | Why the group was skipped (if applicable) |

### `stack_config`

The `StackConfig` used for the stack run, recorded for reproducibility.

## Using the manifest

### Re-run stacking

Since the manifest stores all search and download metadata, you can re-run
`edown stack` without repeating the search or download:

```bash
edown stack --manifest-path data/manifests/run-20240602T143022Z.json
```

### Programmatic access

```python
import json
from pathlib import Path

manifest = json.loads(Path("data/manifests/run-20240602T143022Z.json").read_text())

# Count results by status
from collections import Counter
statuses = Counter(r["status"] for r in manifest["download"]["results"])
print(statuses)

# List failed images
for result in manifest["download"]["results"]:
    if result["status"] == "failed":
        print(f"FAILED: {result['image_id']} -- {result['error']}")
```

### Inspect alignment groups

```python
for group in manifest["search"]["alignment_groups"]:
    print(f"Group {group['group_id']}: {len(group['image_ids'])} images, "
          f"CRS={group['crs']}, {group['width']}x{group['height']} px")
```
