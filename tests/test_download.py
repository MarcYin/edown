from pathlib import Path

import numpy as np
import rasterio

from edown import AOI, DownloadConfig, SearchConfig
from edown.discovery import search_images
from edown.download import download_images
from tests.conftest import make_feature


def test_download_images_writes_geotiffs(tmp_path: Path, monkeypatch) -> None:
    features = [
        make_feature("IMG_1", time_start=1717200000000),
        make_feature("IMG_2", time_start=1717286400000),
    ]
    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range",
        lambda config, start, end: features,
    )
    search_config = SearchConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-02",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04", "B08"),
    )
    result = search_images(search_config)

    monkeypatch.setattr("edown.download.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr("edown.download.search_images", lambda config: result)

    def fake_fetch(job, task, config):
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
    summary = download_images(config)
    assert summary.downloaded == 2
    outputs = [result.tiff_path for result in summary.results if result.tiff_path is not None]
    assert len(outputs) == 2
    with rasterio.open(outputs[0]) as dataset:
        assert dataset.count == 2
