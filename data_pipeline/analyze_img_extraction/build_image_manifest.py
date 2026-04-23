from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_DECADE_SAMPLE_COUNT = 12
DEFAULT_YEAR_PREVIEW_COUNT = 8

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parent.parent
DEFAULT_SOURCE_DIR = ROOT / "output" / "extracted_images"
DEFAULT_GALLERY_DIR = THIS_DIR / "gallery"

FILENAME_PATTERN = re.compile(
    r"_page-(?P<page>\d+)_region-(?P<region>\d+)_(?P<label>.+)\.[^.]+$",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build decade/year manifests for the extracted image gallery."
    )
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Directory containing extracted image crops.",
    )
    parser.add_argument(
        "--gallery-dir",
        default=str(DEFAULT_GALLERY_DIR),
        help="Gallery directory that will receive manifest data.",
    )
    parser.add_argument(
        "--decade-sample-count",
        type=int,
        default=DEFAULT_DECADE_SAMPLE_COUNT,
        help="Number of preview images to include in each decade summary.",
    )
    parser.add_argument(
        "--year-preview-count",
        type=int,
        default=DEFAULT_YEAR_PREVIEW_COUNT,
        help="Number of preview images to include in each year summary.",
    )
    return parser.parse_args()


def decade_label(year: int) -> str:
    return "{}s".format((year // 10) * 10)


def decade_data_filename(decade: str) -> str:
    return "{}.json".format(decade)


def iter_image_paths(source_dir: Path) -> Iterable[Path]:
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        yield path


def parse_item(path: Path, source_dir: Path) -> Dict:
    relative_path = path.relative_to(source_dir)
    parts = relative_path.parts
    if len(parts) < 4:
        raise ValueError("Unexpected extracted image path: {}".format(relative_path))

    year = int(parts[0])
    month = parts[1]
    doc_id = parts[2]
    filename = parts[-1]
    match = FILENAME_PATTERN.search(filename)

    page_number = int(match.group("page")) if match else None
    region_index = int(match.group("region")) if match else None
    raw_label = match.group("label") if match else "unknown"
    label = raw_label.replace("-", " ")
    decade = decade_label(year)

    return {
        "year": year,
        "month": month,
        "decade": decade,
        "doc_id": doc_id,
        "filename": filename,
        "label": label,
        "page_number": page_number,
        "region_index": region_index,
        "source_relative_path": relative_path.as_posix(),
        "full_image_path": "../../../output/extracted_images/{}".format(
            relative_path.as_posix()
        ),
        "thumbnail_path": "thumbs/{}".format(
            relative_path.with_suffix(".jpg").as_posix()
        ),
    }


def preview_item(item: Dict) -> Dict:
    return {
        "doc_id": item["doc_id"],
        "label": item["label"],
        "year": item["year"],
        "month": item["month"],
        "page_number": item["page_number"],
        "region_index": item["region_index"],
        "full_image_path": item["full_image_path"],
        "thumbnail_path": item["thumbnail_path"],
    }


def build_manifest(
    source_dir: Path,
    gallery_dir: Path,
    decade_sample_count: int = DEFAULT_DECADE_SAMPLE_COUNT,
    year_preview_count: int = DEFAULT_YEAR_PREVIEW_COUNT,
) -> Dict:
    if not source_dir.exists():
        raise FileNotFoundError("Missing extracted image directory: {}".format(source_dir))

    data_dir = gallery_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    items = [parse_item(path, source_dir) for path in iter_image_paths(source_dir)]
    items.sort(
        key=lambda item: (
            item["year"],
            item["month"],
            item["doc_id"],
            item["page_number"] or 0,
            item["region_index"] or 0,
            item["filename"],
        )
    )

    decades: Dict[str, Dict[int, List[Dict]]] = defaultdict(lambda: defaultdict(list))
    for item in items:
        decades[item["decade"]][item["year"]].append(item)

    generated_at = datetime.now(timezone.utc).isoformat()
    index_payload = {
        "generated_at": generated_at,
        "source_dir": str(source_dir),
        "total_images": len(items),
        "decades": [],
    }

    for decade in sorted(decades.keys()):
        years_payload = []
        decade_items: List[Dict] = []

        for year in sorted(decades[decade].keys()):
            year_items = decades[decade][year]
            decade_items.extend(year_items)
            years_payload.append(
                {
                    "year": year,
                    "image_count": len(year_items),
                    "preview_items": [
                        preview_item(item) for item in year_items[:year_preview_count]
                    ],
                    "items": year_items,
                }
            )

        decade_payload = {
            "generated_at": generated_at,
            "decade": decade,
            "image_count": len(decade_items),
            "year_count": len(years_payload),
            "years": years_payload,
        }

        decade_output_path = data_dir / decade_data_filename(decade)
        decade_output_path.write_text(
            json.dumps(decade_payload, indent=2),
            encoding="utf-8",
        )

        index_payload["decades"].append(
            {
                "decade": decade,
                "image_count": len(decade_items),
                "year_count": len(years_payload),
                "years": [
                    {"year": year_payload["year"], "image_count": year_payload["image_count"]}
                    for year_payload in years_payload
                ],
                "preview_items": [
                    preview_item(item) for item in decade_items[:decade_sample_count]
                ],
                "data_path": "data/{}".format(decade_data_filename(decade)),
            }
        )

    index_output_path = data_dir / "index.json"
    index_output_path.write_text(
        json.dumps(index_payload, indent=2),
        encoding="utf-8",
    )

    return {
        "generated_at": generated_at,
        "total_images": len(items),
        "decade_count": len(index_payload["decades"]),
        "index_path": index_output_path,
    }


def main() -> None:
    args = parse_args()
    summary = build_manifest(
        source_dir=Path(args.source_dir).resolve(),
        gallery_dir=Path(args.gallery_dir).resolve(),
        decade_sample_count=args.decade_sample_count,
        year_preview_count=args.year_preview_count,
    )
    print("Built {} decade manifests".format(summary["decade_count"]))
    print("Indexed {} extracted images".format(summary["total_images"]))
    print("Index manifest: {}".format(summary["index_path"]))


if __name__ == "__main__":
    main()

