from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional, cast

from .constants import MANIFEST_SCHEMA_VERSION
from .models import DownloadSummary, SearchResult, StackResult
from .utils import run_timestamp, to_jsonable


def default_manifest_path(output_root: Path) -> Path:
    return output_root / "manifests" / f"run-{run_timestamp()}.json"


def build_manifest_document(
    config: Any,
    search_result: SearchResult,
    download_summary: Optional[DownloadSummary] = None,
    stack_results: Optional[Sequence[StackResult]] = None,
    stack_config: Optional[Any] = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "config": to_jsonable(config),
        "search": to_jsonable(search_result),
    }
    if download_summary is not None:
        document["download"] = to_jsonable(download_summary)
    if stack_results is not None:
        document["stack"] = to_jsonable(tuple(stack_results))
    if stack_config is not None:
        document["stack_config"] = to_jsonable(stack_config)
    return document


def write_manifest(path: Path, document: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
