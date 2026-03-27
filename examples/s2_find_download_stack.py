# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from edown import AOI, DownloadConfig, SearchConfig, StackConfig
from edown.discovery import search_images
from edown.download import download_images
from edown.stack import stack_images


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find Sentinel-2 scenes in Earth Engine, "
            "download GeoTIFFs, and build Zarr stacks."
        )
    )
    parser.add_argument(
        "--collection-id",
        default="COPERNICUS/S2_SR_HARMONIZED",
        help="Earth Engine ImageCollection id.",
    )
    parser.add_argument("--start-date", default="2024-06-01", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--end-date", default="2024-06-03", help="Inclusive YYYY-MM-DD.")
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=(-0.1278, 51.5072, -0.1270, 51.5078),
        metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
        help="AOI bounding box in WGS84. Defaults to a tiny London smoke-test AOI.",
    )
    parser.add_argument(
        "--band",
        dest="bands",
        action="append",
        default=None,
        help="Band id to request. Repeat to add more bands.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/live-s2"),
        help="Directory for GeoTIFFs, manifests, and stacks.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing downloads and stacks.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    aoi = AOI.from_bbox(tuple(args.bbox))
    bands = tuple(dict.fromkeys(args.bands or ["B4", "B8"]))

    search_config = SearchConfig(
        collection_id=args.collection_id,
        start_date=args.start_date,
        end_date=args.end_date,
        aoi=aoi,
        bands=bands,
    )
    search_result = search_images(search_config)
    print(f"found {len(search_result.images)} image(s)")
    for image in search_result.images:
        print(image.image_id)

    download_summary = download_images(
        DownloadConfig(
            collection_id=args.collection_id,
            start_date=args.start_date,
            end_date=args.end_date,
            aoi=aoi,
            bands=bands,
            output_root=args.output_root,
            chunk_size=256,
            chunk_size_mode="fixed",
            prepare_workers=1,
            download_workers=1,
            max_inflight_chunks=1,
            max_retries=2,
            retry_delay_seconds=1.0,
            request_byte_limit=8 * 1024 * 1024,
            overwrite=args.overwrite,
        )
    )
    print(f"manifest: {download_summary.manifest_path}")
    print(
        "downloads: "
        f"downloaded={download_summary.downloaded} "
        f"skipped={download_summary.skipped} "
        f"failed={download_summary.failed}"
    )

    stack_results = stack_images(
        StackConfig(
            manifest_path=download_summary.manifest_path,
            output_root=args.output_root,
            backend="threads",
            overwrite=args.overwrite,
        )
    )
    for result in stack_results:
        if result.output_path is not None and result.skipped_reason is None:
            print(f"stack: {result.output_path}")
        else:
            print(f"stack skipped for {result.group_id}: {result.skipped_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
