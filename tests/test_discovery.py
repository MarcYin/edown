from edown import AOI, SearchConfig
from edown.discovery import search_images
from tests.conftest import make_feature


def test_search_images_groups_native_grids(monkeypatch) -> None:
    features = [
        make_feature("IMG_1", time_start=1717200000000),
        make_feature("IMG_2", time_start=1717286400000),
        make_feature(
            "IMG_3",
            transform=(0.2, 0.0, -1.0, 0.0, -0.2, 1.0),
            time_start=1717372800000,
        ),
    ]
    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range",
        lambda config, start, end: features,
    )

    config = SearchConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-03",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04", "B08"),
    )
    result = search_images(config)
    assert len(result.images) == 3
    assert len(result.alignment_groups) == 2
    assert result.output_band_names == ("B04", "B08")


def test_search_images_marks_missing_bands(monkeypatch) -> None:
    features = [
        make_feature("IMG_1", bands=("B04", "B08")),
        make_feature("IMG_2", bands=("B04",)),
    ]
    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range",
        lambda config, start, end: features,
    )

    config = SearchConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-02",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04", "B08"),
    )
    result = search_images(config)
    missing = [image for image in result.images if image.missing_band_ids]
    assert len(missing) == 1
    assert missing[0].missing_band_ids == ("B08",)


def test_search_images_resolves_zero_padded_band_aliases(monkeypatch) -> None:
    features = [make_feature("IMG_1", bands=("B4", "B8"))]
    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range",
        lambda config, start, end: features,
    )

    config = SearchConfig(
        collection_id="COPERNICUS/S2_SR_HARMONIZED",
        start_date="2024-06-01",
        end_date="2024-06-03",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04", "B08"),
        rename_map={"B04": "red", "B08": "nir"},
    )
    result = search_images(config)
    assert result.selected_band_ids == ("B4", "B8")
    assert result.output_band_names == ("red", "nir")


def test_normalize_image_ids_accepts_asset_paths_and_bare_indices() -> None:
    from edown.discovery import normalize_image_ids

    assert normalize_image_ids(
        [
            "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED/20181120T074211_20181120T074211_T37PDL",
            "20181105T074109_20181105T075529_T37PDL",
            "  ",
            "20181120T074211_20181120T074211_T37PDL",
        ]
    ) == (
        "20181120T074211_20181120T074211_T37PDL",
        "20181105T074109_20181105T075529_T37PDL",
    )


class _RecordingCollection:
    """Minimal ee.ImageCollection stand-in that records the filters applied."""

    def __init__(self, calls: list) -> None:
        self.calls = calls

    def filterDate(self, start, end):  # noqa: N802 - mirrors the Earth Engine API
        self.calls.append(("filterDate", start, end))
        return self

    def filterBounds(self, geometry):  # noqa: N802 - mirrors the Earth Engine API
        self.calls.append(("filterBounds",))
        return self

    def filter(self, spec):
        self.calls.append(("filter", spec))
        return self


def _fake_ee(calls: list, monkeypatch):
    import sys
    import types

    module = types.ModuleType("ee")
    module.ImageCollection = lambda collection_id: _RecordingCollection(calls)
    module.Filter = types.SimpleNamespace(
        inList=lambda key, values: ("inList", key, tuple(values))
    )
    monkeypatch.setitem(sys.modules, "ee", module)


def _config(**kwargs):
    return SearchConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-03",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04",),
        **kwargs,
    )


def test_image_ids_filter_narrows_the_query_itself(monkeypatch) -> None:
    # Server-side, so counts and recursive date splitting shrink with the
    # selection instead of transferring a whole window to discard most of it.
    from datetime import datetime, timezone

    from edown.discovery import _build_collection

    calls: list = []
    _fake_ee(calls, monkeypatch)
    monkeypatch.setattr(AOI, "to_ee_geometry", lambda self: None)
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 3, tzinfo=timezone.utc)

    _build_collection(_config(image_ids=("COLL/IMG_1", "IMG_2")), start, end)
    assert ("filter", ("inList", "system:index", ("IMG_1", "IMG_2"))) in calls


def test_no_image_ids_leaves_the_query_unfiltered(monkeypatch) -> None:
    from datetime import datetime, timezone

    from edown.discovery import _build_collection

    calls: list = []
    _fake_ee(calls, monkeypatch)
    monkeypatch.setattr(AOI, "to_ee_geometry", lambda self: None)
    _build_collection(
        _config(), datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 3, tzinfo=timezone.utc)
    )
    assert not any(call[0] == "filter" for call in calls)


def test_unmatched_image_ids_are_reported_not_silently_dropped(monkeypatch, caplog) -> None:
    # A requested id that matches nothing looks exactly like a missing
    # acquisition downstream, so it has to be said out loud.
    features = [make_feature("COLL/IMG_1")]
    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range", lambda config, start, end: features
    )
    with caplog.at_level("WARNING"):
        result = search_images(_config(image_ids=("IMG_1", "IMG_MISSING")))
    assert len(result.images) == 1
    assert "IMG_MISSING" in caplog.text
