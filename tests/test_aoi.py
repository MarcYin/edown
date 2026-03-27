from pathlib import Path

from edown import AOI


def test_aoi_from_bbox() -> None:
    aoi = AOI.from_bbox((-1.0, -2.0, 3.0, 4.0))
    assert aoi.bounds == (-1.0, -2.0, 3.0, 4.0)


def test_aoi_from_geojson(sample_geojson: Path) -> None:
    aoi = AOI.from_geojson(sample_geojson)
    assert aoi.bounds == (-0.5, -0.5, 0.5, 0.5)
