from pyproj import CRS, Transformer

from edown.crs import proj_crs_for


def test_modis_sinusoidal_code_is_resolved() -> None:
    # SR-ORG:6974 is the EE identifier for MODIS sinusoidal; PROJ cannot resolve
    # it directly, so proj_crs_for must return a usable definition.
    resolved = proj_crs_for("SR-ORG:6974")
    assert resolved != "SR-ORG:6974"
    crs = CRS.from_user_input(resolved)
    assert crs.coordinate_operation is not None
    # A transform that previously raised "crs not found" must now build.
    Transformer.from_crs("EPSG:4326", resolved, always_xy=True)


def test_older_modis_code_is_resolved() -> None:
    assert proj_crs_for("SR-ORG:6842") == proj_crs_for("SR-ORG:6974")


def test_case_insensitive_lookup() -> None:
    assert proj_crs_for("sr-org:6974") == proj_crs_for("SR-ORG:6974")


def test_standard_codes_pass_through() -> None:
    assert proj_crs_for("EPSG:4326") == "EPSG:4326"
    assert proj_crs_for("EPSG:32631") == "EPSG:32631"


def test_non_string_passes_through() -> None:
    assert proj_crs_for(None) is None  # type: ignore[arg-type]
