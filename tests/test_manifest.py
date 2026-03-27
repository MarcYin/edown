from pathlib import Path

from edown import AOI, SearchConfig
from edown.discovery import search_images
from edown.manifest import build_manifest_document, load_manifest, write_manifest
from tests.conftest import make_feature


def test_manifest_round_trip(tmp_path: Path, monkeypatch) -> None:
    features = [make_feature("IMG_1")]
    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range",
        lambda config, start, end: features,
    )

    config = SearchConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-01",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04",),
    )
    result = search_images(config)
    manifest_path = tmp_path / "manifest.json"
    document = build_manifest_document(config, result)
    write_manifest(manifest_path, document)
    loaded = load_manifest(manifest_path)
    assert loaded["search"]["collection_id"] == "TEST/COLLECTION"
    assert loaded["search"]["images"][0]["image_id"] == "IMG_1"
