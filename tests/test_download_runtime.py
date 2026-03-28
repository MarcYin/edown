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


def test_positive_y_scale_grid_downloads_when_aoi_intersects(tmp_path: Path, monkeypatch) -> None:
    feature = make_feature("IMG_POS_Y", transform=(0.1, 0.0, -1.0, 0.0, 0.1, -1.0))
    result = _search_result(monkeypatch, [feature])
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

    assert summary.downloaded == 1
    assert summary.results[0].status == "downloaded"


def test_download_progress_receives_tile_and_chunk_updates(tmp_path: Path, monkeypatch) -> None:
    result = _search_result(monkeypatch, [make_feature("IMG_1")])
    monkeypatch.setattr("edown.download.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr("edown.download.search_images", lambda config: result)

    def fake_fetch(job, task, config):
        import numpy as np

        row, col, chunk_h, chunk_w = task
        data = np.ones((chunk_h, chunk_w, len(job.image.selected_band_ids)), dtype=np.float32)
        return row, col, data

    monkeypatch.setattr("edown.download._fetch_chunk", fake_fetch)

    class Recorder:
        def __init__(self) -> None:
            self.events: list[tuple[str, object]] = []

        def on_search_result(self, image_ids) -> None:
            self.events.append(("search", tuple(image_ids)))

        def on_prepare_result(self, result) -> None:
            self.events.append(("prepare_result", result.image_id))

        def on_job_prepared(self, image_id: str, chunk_count: int) -> None:
            self.events.append(("prepared", (image_id, chunk_count)))

        def on_job_chunk_grid(
            self,
            image_id: str,
            chunk_rows: int,
            chunk_cols: int,
            active_cells,
        ) -> None:
            self.events.append(("grid", (image_id, chunk_rows, chunk_cols, tuple(active_cells))))

        def on_chunk_complete(self, image_id: str) -> None:
            self.events.append(("chunk", image_id))

        def on_chunk_cell_complete(self, image_id: str, chunk_row: int, chunk_col: int) -> None:
            self.events.append(("cell", (image_id, chunk_row, chunk_col)))

        def on_job_failed(self, image_id: str, error: str) -> None:
            self.events.append(("failed", image_id))

        def on_job_finished(self, result) -> None:
            self.events.append(("finished", (result.image_id, result.status)))

        def close(self) -> None:
            self.events.append(("closed", None))

    progress = Recorder()
    summary = download_images(
        DownloadConfig(
            collection_id="TEST/COLLECTION",
            start_date="2024-06-01",
            end_date="2024-06-02",
            aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
            bands=("B04", "B08"),
            output_root=tmp_path,
        ),
        progress=progress,
    )

    assert summary.downloaded == 1
    assert ("search", ("IMG_1",)) in progress.events
    prepared_events = [
        payload for event, payload in progress.events if event == "prepared"
    ]
    assert prepared_events
    image_id, chunk_count = prepared_events[0]
    assert image_id == "IMG_1"
    grid_events = [payload for event, payload in progress.events if event == "grid"]
    assert grid_events
    grid_image_id, grid_rows, grid_cols, active_cells = grid_events[0]
    assert grid_image_id == "IMG_1"
    assert (grid_rows, grid_cols) == (2, 2)
    assert active_cells == ((0, 0), (0, 1), (1, 0), (1, 1))
    chunk_events = [payload for event, payload in progress.events if event == "chunk"]
    assert len(chunk_events) == chunk_count
    cell_events = [payload for event, payload in progress.events if event == "cell"]
    assert len(cell_events) == chunk_count
    assert set(cell_events) == {
        ("IMG_1", 0, 0),
        ("IMG_1", 0, 1),
        ("IMG_1", 1, 0),
        ("IMG_1", 1, 1),
    }
    assert ("finished", ("IMG_1", "downloaded")) in progress.events
    assert progress.events[-1] == ("closed", None)


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
