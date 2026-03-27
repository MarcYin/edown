from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import pytest


def make_feature(
    image_id: str,
    *,
    transform: Optional[Sequence[float]] = None,
    bands: Sequence[str] = ("B04", "B08"),
    precision: str = "uint16",
    time_start: int = 1717200000000,
) -> dict:
    grid_transform = list(transform or (0.1, 0.0, -1.0, 0.0, -0.1, 1.0))
    return {
        "id": image_id,
        "version": 1,
        "bands": [
            {
                "id": band,
                "crs": "EPSG:4326",
                "crs_transform": grid_transform,
                "dimensions": [20, 20],
                "data_type": {"precision": precision},
            }
            for band in bands
        ],
        "properties": {"system:time_start": time_start},
    }


@pytest.fixture
def sample_geojson(tmp_path: Path) -> Path:
    path = tmp_path / "aoi.geojson"
    path.write_text(
        """
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-0.5, 0.5], [0.5, 0.5], [0.5, -0.5], [-0.5, -0.5], [-0.5, 0.5]]]
      }
    }
  ]
}
        """.strip(),
        encoding="utf-8",
    )
    return path
