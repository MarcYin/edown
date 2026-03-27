from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

from shapely.geometry import GeometryCollection, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .errors import ConfigurationError


def _geometry_from_geojson_payload(payload: dict[str, Any]) -> BaseGeometry:
    geojson_type = payload.get("type")
    if geojson_type == "FeatureCollection":
        geometries = [
            shape(feature["geometry"])
            for feature in payload.get("features", [])
            if feature.get("geometry") is not None
        ]
        if not geometries:
            raise ConfigurationError("GeoJSON FeatureCollection contains no geometries.")
        return unary_union(geometries)
    if geojson_type == "Feature":
        geometry = payload.get("geometry")
        if geometry is None:
            raise ConfigurationError("GeoJSON Feature is missing geometry.")
        return shape(geometry)
    if geojson_type is not None and "coordinates" in payload:
        return shape(payload)
    raise ConfigurationError("Unsupported GeoJSON payload.")


@dataclass(frozen=True)
class AOI:
    geometry: BaseGeometry
    geojson_path: Optional[Path] = None

    @classmethod
    def from_bbox(cls, bbox: Tuple[float, float, float, float]) -> "AOI":
        from shapely.geometry import box

        xmin, ymin, xmax, ymax = bbox
        if xmin >= xmax or ymin >= ymax:
            raise ConfigurationError("bbox must be xmin < xmax and ymin < ymax.")
        return cls(geometry=box(xmin, ymin, xmax, ymax))

    @classmethod
    def from_geojson(cls, geojson_path: Path) -> "AOI":
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        geometry = _geometry_from_geojson_payload(payload)
        if isinstance(geometry, GeometryCollection) and geometry.is_empty:
            raise ConfigurationError("GeoJSON geometry is empty.")
        return cls(geometry=geometry, geojson_path=geojson_path)

    @classmethod
    def from_inputs(
        cls,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        geojson_path: Optional[Path] = None,
    ) -> "AOI":
        if bbox is not None and geojson_path is not None:
            raise ConfigurationError("Specify either bbox or geojson_path, not both.")
        if bbox is None and geojson_path is None:
            raise ConfigurationError("Specify either bbox or geojson_path.")
        if bbox is not None:
            return cls.from_bbox(bbox)
        assert geojson_path is not None
        return cls.from_geojson(geojson_path)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xmin, ymin, xmax, ymax = self.geometry.bounds
        return float(xmin), float(ymin), float(xmax), float(ymax)

    def to_ee_geometry(self) -> Any:
        import ee
        from shapely.geometry import mapping

        return ee.Geometry(mapping(self.geometry), proj="EPSG:4326", geodesic=False)
