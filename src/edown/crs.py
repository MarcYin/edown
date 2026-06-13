"""Coordinate-reference-system helpers.

Earth Engine identifies some collections (notably the MODIS land products) by
legacy ``SR-ORG`` authority codes such as ``SR-ORG:6974``. Earth Engine itself
understands these codes, but PROJ/pyproj do not, so any local geometry math or
GeoTIFF tagging that feeds the raw code to PROJ fails with
``proj_create: crs not found``.

These helpers translate the EE-only codes into a PROJ-resolvable definition for
local use while leaving the original string intact for the Earth Engine request
grid (``crsCode``), which must keep the EE code.
"""

from __future__ import annotations

# MODIS sinusoidal on the authalic sphere (R = 6371007.181 m) as used by the
# MODIS/VIIRS land products. Earth Engine reports this grid as SR-ORG:6974
# (and the older SR-ORG:6842); both map to the same definition for PROJ.
_MODIS_SINUSOIDAL_PROJ4 = (
    "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs +type=crs"
)

#: EE-only CRS identifiers that PROJ cannot resolve, mapped to a PROJ-usable
#: definition. Keys are compared case-insensitively.
_EE_CRS_OVERRIDES: dict[str, str] = {
    "SR-ORG:6974": _MODIS_SINUSOIDAL_PROJ4,
    "SR-ORG:6842": _MODIS_SINUSOIDAL_PROJ4,
}


def proj_crs_for(ee_crs: str) -> str:
    """Return a PROJ-resolvable CRS string for an Earth Engine CRS identifier.

    Known EE-only codes (e.g. ``SR-ORG:6974`` for MODIS sinusoidal) are mapped
    to an equivalent proj4 definition. Standard authority codes (``EPSG:...``)
    and WKT strings are returned unchanged, so this is safe to apply at every
    PROJ/rasterio boundary.
    """
    if not isinstance(ee_crs, str):
        return ee_crs
    return _EE_CRS_OVERRIDES.get(ee_crs.strip().upper(), ee_crs)
