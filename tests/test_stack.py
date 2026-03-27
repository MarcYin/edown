from pathlib import Path

import rasterio

from edown import AOI, DownloadConfig, SearchConfig, StackConfig
from edown.discovery import search_images
from edown.download import download_images
from edown.stack import stack_images
from tests.conftest import make_feature


def test_stack_images_builds_zarr(tmp_path: Path, monkeypatch) -> None:
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
        import numpy as np

        row, col, chunk_h, chunk_w = task
        data = np.ones((chunk_h, chunk_w, len(job.image.selected_band_ids)), dtype=np.float32)
        return row, col, data

    monkeypatch.setattr("edown.download._fetch_chunk", fake_fetch)

    download_config = DownloadConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-02",
        aoi=AOI.from_bbox((-0.5, -0.5, 0.5, 0.5)),
        bands=("B04", "B08"),
        output_root=tmp_path,
    )
    summary = download_images(download_config)
    stack_results = stack_images(
        StackConfig(
            manifest_path=summary.manifest_path,
            output_root=tmp_path,
            backend="threads",
        )
    )
    successful = [result for result in stack_results if result.output_path is not None]
    assert successful
    assert successful[0].output_path is not None
    assert Path(successful[0].output_path).exists()


def test_stack_images_uses_clipped_tiff_grid(tmp_path: Path, monkeypatch) -> None:
    features = [
        make_feature("IMG_1", time_start=1717200000000),
        make_feature("IMG_2", time_start=1717286400000),
    ]
    for feature in features:
        for band in feature["bands"]:
            band["dimensions"] = [100, 100]
            band["crs_transform"] = [0.1, 0.0, -5.0, 0.0, -0.1, 5.0]

    monkeypatch.setattr("edown.discovery.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr(
        "edown.discovery._collect_features_for_range",
        lambda config, start, end: features,
    )
    search_config = SearchConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-02",
        aoi=AOI.from_bbox((-0.05, -0.05, 0.05, 0.05)),
        bands=("B04", "B08"),
    )
    result = search_images(search_config)

    monkeypatch.setattr("edown.download.initialize_earth_engine", lambda server_url: "default")
    monkeypatch.setattr("edown.download.search_images", lambda config: result)

    def fake_fetch(job, task, config):
        import numpy as np

        row, col, chunk_h, chunk_w = task
        data = np.ones((chunk_h, chunk_w, len(job.image.selected_band_ids)), dtype=np.float32)
        return row, col, data

    monkeypatch.setattr("edown.download._fetch_chunk", fake_fetch)

    download_config = DownloadConfig(
        collection_id="TEST/COLLECTION",
        start_date="2024-06-01",
        end_date="2024-06-02",
        aoi=AOI.from_bbox((-0.05, -0.05, 0.05, 0.05)),
        bands=("B04", "B08"),
        output_root=tmp_path,
        chunk_size=16,
        chunk_size_mode="fixed",
    )
    summary = download_images(download_config)
    downloaded = [result for result in summary.results if result.tiff_path is not None]
    assert downloaded

    stack_results = stack_images(
        StackConfig(
            manifest_path=summary.manifest_path,
            output_root=tmp_path,
            backend="threads",
        )
    )
    successful = [result for result in stack_results if result.output_path is not None]
    assert successful
    assert successful[0].output_path is not None

    import xarray as xr

    with rasterio.open(downloaded[0].tiff_path) as dataset:
        expected_width = dataset.width
        expected_height = dataset.height
        expected_transform = (
            float(dataset.transform.a),
            float(dataset.transform.b),
            float(dataset.transform.c),
            float(dataset.transform.d),
            float(dataset.transform.e),
            float(dataset.transform.f),
        )

    zarr_dataset = xr.open_zarr(successful[0].output_path)
    try:
        assert zarr_dataset.sizes["x"] == expected_width
        assert zarr_dataset.sizes["y"] == expected_height
        assert tuple(zarr_dataset["data"].attrs["transform"]) == expected_transform
    finally:
        zarr_dataset.close()
