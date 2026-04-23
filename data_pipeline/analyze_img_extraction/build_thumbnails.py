from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, Optional

from build_image_manifest import DEFAULT_GALLERY_DIR, DEFAULT_SOURCE_DIR, iter_image_paths


DEFAULT_MAX_EDGE = 280
DEFAULT_QUALITY = 82


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build thumbnails for the extracted image gallery."
    )
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Directory containing extracted image crops.",
    )
    parser.add_argument(
        "--gallery-dir",
        default=str(DEFAULT_GALLERY_DIR),
        help="Gallery directory that will receive thumbnail images.",
    )
    parser.add_argument(
        "--max-edge",
        type=int,
        default=DEFAULT_MAX_EDGE,
        help="Maximum width or height of a thumbnail in pixels.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        help="JPEG quality for thumbnails.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Optional start year filter.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Optional end year filter.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional image limit for testing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate thumbnails even when they already exist.",
    )
    return parser.parse_args()


def require_pillow():
    try:
        from PIL import Image, ImageOps  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Pillow is required to build thumbnails. Install it with 'python3 -m pip install Pillow'."
        ) from exc
    return Image, ImageOps


def thumbnail_output_path(source_path: Path, source_dir: Path, gallery_dir: Path) -> Path:
    relative_path = source_path.relative_to(source_dir)
    return gallery_dir / "thumbs" / relative_path.with_suffix(".jpg")


def year_from_path(source_path: Path, source_dir: Path) -> int:
    return int(source_path.relative_to(source_dir).parts[0])


def filtered_image_paths(
    source_dir: Path,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    limit: Optional[int] = None,
) -> Iterable[Path]:
    count = 0
    for path in iter_image_paths(source_dir):
        year = year_from_path(path, source_dir)
        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue
        yield path
        count += 1
        if limit is not None and count >= limit:
            return


def save_thumbnail(
    source_path: Path,
    output_path: Path,
    max_edge: int,
    quality: int,
) -> None:
    Image, ImageOps = require_pillow()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        normalized = ImageOps.exif_transpose(image)
        normalized.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

        if normalized.mode not in ("RGB", "L"):
            background = Image.new("RGB", normalized.size, (247, 244, 237))
            alpha = normalized.getchannel("A") if "A" in normalized.getbands() else None
            background.paste(normalized.convert("RGB"), mask=alpha)
            normalized = background
        elif normalized.mode == "L":
            normalized = normalized.convert("RGB")

        normalized.save(output_path, format="JPEG", quality=quality, optimize=True)


def build_thumbnails(
    source_dir: Path,
    gallery_dir: Path,
    max_edge: int = DEFAULT_MAX_EDGE,
    quality: int = DEFAULT_QUALITY,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    limit: Optional[int] = None,
    force: bool = False,
) -> Dict:
    if not source_dir.exists():
        raise FileNotFoundError("Missing extracted image directory: {}".format(source_dir))

    require_pillow()

    processed = 0
    skipped = 0

    for source_path in filtered_image_paths(
        source_dir=source_dir,
        start_year=start_year,
        end_year=end_year,
        limit=limit,
    ):
        output_path = thumbnail_output_path(source_path, source_dir, gallery_dir)
        if output_path.exists() and not force:
            skipped += 1
            continue

        save_thumbnail(
            source_path=source_path,
            output_path=output_path,
            max_edge=max_edge,
            quality=quality,
        )
        processed += 1

    return {
        "processed": processed,
        "skipped": skipped,
        "thumbnail_root": gallery_dir / "thumbs",
    }


def main() -> None:
    args = parse_args()
    try:
        summary = build_thumbnails(
            source_dir=Path(args.source_dir).resolve(),
            gallery_dir=Path(args.gallery_dir).resolve(),
            max_edge=args.max_edge,
            quality=args.quality,
            start_year=args.start_year,
            end_year=args.end_year,
            limit=args.limit,
            force=args.force,
        )
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    print("Built {} thumbnails".format(summary["processed"]))
    print("Skipped {} existing thumbnails".format(summary["skipped"]))
    print("Thumbnail root: {}".format(summary["thumbnail_root"]))


if __name__ == "__main__":
    main()
