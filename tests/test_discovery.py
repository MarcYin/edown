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
