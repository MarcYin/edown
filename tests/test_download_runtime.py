from pathlib import Path

from edown import AOI, DownloadConfig, SearchConfig, StackConfig
from edown.discovery import search_images
from edown.download import download_images
from edown.manifest import load_manifest
from edown.stack import stack_images
from tests.conftest import make_feature


def _search_result(monkeypatch, features):
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
    return search_images(config)


def test_prepare_failure_becomes_failed_result(tmp_path: Path, monkeypatch) -> None:
    result = _search_result(monkeypatch, [make_feature("IMG_1")])
    monkeypatch.setattr("edown.download.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr("edown.download.search_images", lambda config: result)
    monkeypatch.setattr(
        "edown.download.get_image_grid_info",
        lambda image_info: (_ for _ in ()).throw(RuntimeError("bad grid")),
    )

    summary = download_images(
        DownloadConfig(
            collection_id="TEST/COLLECTION",
            start_date="2024-06-01",
            end_date="2024-06-02",
            aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
            bands=("B04", "B08"),
            output_root=tmp_path,
        )
    )
    assert summary.failed == 1
    assert summary.results[0].status == "failed"
    assert "Preparation failed" in (summary.results[0].error or "")


def test_resume_skips_existing_outputs(tmp_path: Path, monkeypatch) -> None:
    result = _search_result(monkeypatch, [make_feature("IMG_1")])
    monkeypatch.setattr("edown.download.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr("edown.download.search_images", lambda config: result)

    def fake_fetch(job, task, config):
        import numpy as np

        row, col, chunk_h, chunk_w = task
        data = np.ones((chunk_h, chunk_w, len(job.image.selected_band_ids)), dtype=np.float32)
        return row, col, data

    monkeypatch.setattr("edown.download._fetch_chunk", fake_fetch)
    config = DownloadConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-02",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04", "B08"),
        output_root=tmp_path,
    )
    first = download_images(config)
    second = download_images(config)

    assert first.downloaded == 1
    assert second.skipped == 1
    assert second.results[0].status == "skipped_existing"


def test_stack_manifest_records_stack_config(tmp_path: Path, monkeypatch) -> None:
    result = _search_result(monkeypatch, [make_feature("IMG_1"), make_feature("IMG_2")])
    monkeypatch.setattr("edown.download.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr("edown.download.search_images", lambda config: result)

    def fake_fetch(job, task, config):
        import numpy as np

        row, col, chunk_h, chunk_w = task
        data = np.ones((chunk_h, chunk_w, len(job.image.selected_band_ids)), dtype=np.float32)
        return row, col, data

    monkeypatch.setattr("edown.download._fetch_chunk", fake_fetch)
    summary = download_images(
        DownloadConfig(
            collection_id="TEST/COLLECTION",
            start_date="2024-06-01",
            end_date="2024-06-02",
            aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
            bands=("B04", "B08"),
            output_root=tmp_path,
        )
    )

    stack_images(
        StackConfig(
            manifest_path=summary.manifest_path,
            output_root=tmp_path,
            backend="threads",
        )
    )
    manifest = load_manifest(summary.manifest_path)
    assert manifest["stack_config"]["backend"] == "threads"
    assert manifest["stack"]
