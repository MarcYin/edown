from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

_BAND_ID_SUFFIX_PATTERN = re.compile(r"^(?P<prefix>[A-Za-z_]+)(?P<digits>\d+)$")


def safe_identifier(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("=", "_")
        .replace(",", "_")
    )


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "__geo_interface__"):
        return value.__geo_interface__
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_timestamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def parse_date_string(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def inclusive_date_range_to_exclusive_end(start_date: str, end_date: str) -> tuple[date, date]:
    start = parse_date_string(start_date)
    end = parse_date_string(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    return start, end + timedelta(days=1)


def ensure_tuple_strings(values: Optional[Sequence[str]]) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(str(value) for value in values)


def band_id_aliases(value: str) -> tuple[str, ...]:
    aliases = [value]
    match = _BAND_ID_SUFFIX_PATTERN.fullmatch(value)
    if match is None:
        return tuple(aliases)

    prefix = match.group("prefix")
    digits = match.group("digits")
    normalized = f"{prefix}{int(digits)}"
    if normalized not in aliases:
        aliases.append(normalized)

    if len(normalized) == len(prefix) + 1:
        padded = f"{prefix}{normalized[len(prefix):].zfill(2)}"
        if padded not in aliases:
            aliases.append(padded)
    return tuple(aliases)


def resolve_requested_band_id(
    requested_band_id: str, available_band_ids: Sequence[str]
) -> Optional[str]:
    for alias in band_id_aliases(requested_band_id):
        if alias in available_band_ids:
            return alias
    return None


def mapping_value_for_band_id(band_id: str, mapping: Mapping[str, Any]) -> Optional[Any]:
    for alias in band_id_aliases(band_id):
        if alias in mapping:
            return mapping[alias]
    return None


def band_output_names(
    band_ids: Sequence[str], rename_map: Mapping[str, str]
) -> tuple[str, ...]:
    output_names: list[str] = []
    for band_id in band_ids:
        renamed = mapping_value_for_band_id(band_id, rename_map)
        output_names.append(str(renamed) if renamed is not None else band_id)
    return tuple(output_names)


def alignment_signature(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
    return digest[:12]


def default_nodata_for_dtype(dtype_name: str) -> Union[float, int]:
    dtype: np.dtype[Any] = np.dtype(dtype_name)
    if np.issubdtype(dtype, np.floating):
        return math.nan
    info = np.iinfo(dtype)
    return int(info.max)


def promote_dtype_name(dtype_name: str) -> str:
    if dtype_name == "int32":
        return "float32"
    if dtype_name == "int64":
        return "float64"
    return dtype_name


def output_tree_paths(output_root: Path, collection_id: str, image_id: str) -> tuple[Path, Path]:
    collection_dir = safe_identifier(collection_id)
    tiff_path = output_root / "images" / collection_dir / f"{safe_identifier(image_id)}.tif"
    metadata_path = Path(f"{tiff_path}.metadata.json")
    return tiff_path, metadata_path


def relative_tiff_path(collection_id: str, image_id: str) -> str:
    return str(Path("images") / safe_identifier(collection_id) / f"{safe_identifier(image_id)}.tif")


def split_csv_values(values: Iterable[str]) -> tuple[str, ...]:
    items = []
    for value in values:
        for chunk in value.split(","):
            stripped = chunk.strip()
            if stripped:
                items.append(stripped)
    return tuple(items)


def serializable_transform(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)
