from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .aoi import AOI
from .constants import (
    DEFAULT_COLLECTION_CHUNK_LIMIT,
    DEFAULT_DOWNLOAD_WORKERS,
    DEFAULT_HIGH_VOLUME_URL,
    DEFAULT_MAX_INFLIGHT_CHUNKS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PREPARE_WORKERS,
    DEFAULT_REQUEST_BYTE_LIMIT,
    DEFAULT_RETRY_DELAY_SECONDS,
)
from .errors import ConfigurationError
from .utils import ensure_tuple_strings, utc_now


@dataclass
class SearchConfig:
    collection_id: str
    start_date: str
    end_date: str
    aoi: AOI
    bands: tuple[str, ...] = ()
    band_include: tuple[str, ...] = ()
    band_exclude: tuple[str, ...] = ()
    rename_map: dict[str, str] = field(default_factory=dict)
    scale_map: dict[str, float] = field(default_factory=dict)
    transform_plugin: Optional[str] = None
    server_url: str = DEFAULT_HIGH_VOLUME_URL
    collection_chunk_limit: int = DEFAULT_COLLECTION_CHUNK_LIMIT

    def __post_init__(self) -> None:
        self.bands = ensure_tuple_strings(self.bands)
        self.band_include = ensure_tuple_strings(self.band_include)
        self.band_exclude = ensure_tuple_strings(self.band_exclude)
        if not self.collection_id:
            raise ConfigurationError("collection_id is required.")


@dataclass
class DownloadConfig(SearchConfig):
    output_root: Path = Path("data")
    manifest_path: Optional[Path] = None
    chunk_size: Optional[int] = None
    chunk_size_mode: str = "auto"
    prepare_workers: int = DEFAULT_PREPARE_WORKERS
    download_workers: int = DEFAULT_DOWNLOAD_WORKERS
    max_inflight_chunks: int = DEFAULT_MAX_INFLIGHT_CHUNKS
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS
    request_byte_limit: int = DEFAULT_REQUEST_BYTE_LIMIT
    overwrite: bool = False
    resume: bool = True
    nodata: Optional[float] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.output_root = Path(self.output_root)
        if self.chunk_size_mode not in {"auto", "fixed"}:
            raise ConfigurationError("chunk_size_mode must be 'auto' or 'fixed'.")
        if self.chunk_size_mode == "fixed" and self.chunk_size is None:
            raise ConfigurationError("chunk_size must be set when chunk_size_mode='fixed'.")


@dataclass
class StackConfig:
    manifest_path: Path
    output_root: Optional[Path] = None
    backend: str = "threads"
    overwrite: bool = False
    n_workers: int = 4
    cores_per_worker: int = 1
    memory_per_worker: str = "1GB"
    slurm_queue: Optional[str] = None
    slurm_account: Optional[str] = None

    def __post_init__(self) -> None:
        self.manifest_path = Path(self.manifest_path)
        if self.output_root is not None:
            self.output_root = Path(self.output_root)
        if self.backend not in {"threads", "dask-local", "dask-slurm"}:
            raise ConfigurationError("backend must be 'threads', 'dask-local', or 'dask-slurm'.")


@dataclass(frozen=True)
class ImageRecord:
    collection_id: str
    image_id: str
    acquisition_time_utc: datetime
    local_datetime: datetime
    properties: dict[str, Any]
    raw_image_info: dict[str, Any]
    available_band_ids: tuple[str, ...]
    selected_band_ids: tuple[str, ...]
    output_band_names: tuple[str, ...]
    missing_band_ids: tuple[str, ...]
    band_byte_sizes: dict[str, int]
    output_dtype: str
    native_crs: str
    native_transform: tuple[float, ...]
    native_width: int
    native_height: int
    native_bounds: tuple[float, float, float, float]
    alignment_signature: str
    relative_tiff_path: str


@dataclass(frozen=True)
class AlignmentGroup:
    group_id: str
    image_ids: tuple[str, ...]
    crs: str
    transform: tuple[float, ...]
    width: int
    height: int
    band_names: tuple[str, ...]
    dtype: str


@dataclass(frozen=True)
class SearchResult:
    collection_id: str
    start_date: str
    end_date: str
    aoi_bounds: tuple[float, float, float, float]
    selected_band_ids: tuple[str, ...]
    output_band_names: tuple[str, ...]
    images: tuple[ImageRecord, ...]
    alignment_groups: tuple[AlignmentGroup, ...]
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class DownloadResult:
    image_id: str
    status: str
    tiff_path: Optional[Path] = None
    metadata_path: Optional[Path] = None
    chunk_count: int = 0
    error: Optional[str] = None


@dataclass(frozen=True)
class DownloadSummary:
    manifest_path: Path
    output_root: Path
    results: tuple[DownloadResult, ...]
    created_at: datetime = field(default_factory=utc_now)

    @property
    def downloaded(self) -> int:
        return sum(1 for result in self.results if result.status == "downloaded")

    @property
    def skipped(self) -> int:
        return sum(1 for result in self.results if result.status.startswith("skipped"))

    @property
    def failed(self) -> int:
        return sum(1 for result in self.results if result.status == "failed")


@dataclass(frozen=True)
class StackResult:
    group_id: str
    image_count: int
    output_path: Optional[Path] = None
    skipped_reason: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
