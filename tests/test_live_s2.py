from __future__ import annotations

import os
from pathlib import Path

import pytest

from edown import AOI, DownloadConfig, SearchConfig, StackConfig
from edown.discovery import search_images
from edown.download import download_images
from edown.stack import stack_images
from edown.utils import resolve_requested_band_id

pytestmark = pytest.mark.live

_DEFAULT_COLLECTION_ID = "COPERNICUS/S2_SR_HARMONIZED"
_DEFAULT_START_DATE = "2024-06-01"
_DEFAULT_END_DATE = "2024-06-03"
_DEFAULT_BBOX = (-0.1278, 51.5072, -0.1270, 51.5078)
_DEFAULT_BANDS = ("B4", "B8")


def _require_live_enabled() -> None:
    if os.environ.get("EDOWN_RUN_LIVE_TESTS") != "1":
        pytest.skip("Set EDOWN_RUN_LIVE_TESTS=1 to run live Earth Engine integration tests.")


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(parts) != 4:
        raise ValueError(
            "EDOWN_LIVE_BBOX must contain four comma-separated numbers: xmin,ymin,xmax,ymax"
        )
    xmin, ymin, xmax, ymax = parts
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("EDOWN_LIVE_BBOX must satisfy xmin < xmax and ymin < ymax")
    return xmin, ymin, xmax, ymax


def _live_settings() -> dict[str, object]:
    bands = tuple(
        item.strip()
        for item in os.environ.get("EDOWN_LIVE_BANDS", ",".join(_DEFAULT_BANDS)).split(",")
        if item.strip()
    )
    if not bands:
        raise ValueError("EDOWN_LIVE_BANDS must contain at least one band id")

    bbox_text = os.environ.get("EDOWN_LIVE_BBOX", ",".join(str(value) for value in _DEFAULT_BBOX))
    return {
        "collection_id": os.environ.get("EDOWN_LIVE_COLLECTION_ID", _DEFAULT_COLLECTION_ID),
        "start_date": os.environ.get("EDOWN_LIVE_START_DATE", _DEFAULT_START_DATE),
        "end_date": os.environ.get("EDOWN_LIVE_END_DATE", _DEFAULT_END_DATE),
        "bbox": _parse_bbox(bbox_text),
        "bands": bands,
    }


def test_live_s2_find_download_and_stack(tmp_path: Path) -> None:
    _require_live_enabled()
    pytest.importorskip("xarray")
    pytest.importorskip("zarr")

    settings = _live_settings()
    aoi = AOI.from_bbox(settings["bbox"])
    bands = settings["bands"]

    search_result = search_images(
        SearchConfig(
            collection_id=str(settings["collection_id"]),
            start_date=str(settings["start_date"]),
            end_date=str(settings["end_date"]),
            aoi=aoi,
            bands=bands,
        )
    )
    assert search_result.images
    assert len(search_result.selected_band_ids) == len(bands)
    assert all(
        resolve_requested_band_id(band, search_result.selected_band_ids) is not None
        for band in bands
    )

    summary = download_images(
        DownloadConfig(
            collection_id=str(settings["collection_id"]),
            start_date=str(settings["start_date"]),
            end_date=str(settings["end_date"]),
            aoi=aoi,
            bands=bands,
            output_root=tmp_path,
            chunk_size=256,
            chunk_size_mode="fixed",
            prepare_workers=1,
            download_workers=1,
            max_inflight_chunks=1,
            max_retries=2,
            retry_delay_seconds=1.0,
            request_byte_limit=8 * 1024 * 1024,
        )
    )
    successful_downloads = [
        result for result in summary.results if result.status in {"downloaded", "skipped_existing"}
    ]
    assert successful_downloads
    assert summary.failed == 0
    assert summary.manifest_path.exists()
    for result in successful_downloads:
        assert result.tiff_path is not None
        assert result.metadata_path is not None
        assert Path(result.tiff_path).exists()
        assert Path(result.metadata_path).exists()

    stack_results = stack_images(
        StackConfig(
            manifest_path=summary.manifest_path,
            output_root=tmp_path,
            backend="threads",
            overwrite=True,
        )
    )
    successful_stacks = [
        result
        for result in stack_results
        if result.output_path is not None and not result.skipped_reason
    ]
    assert successful_stacks
    assert Path(successful_stacks[0].output_path).exists()
