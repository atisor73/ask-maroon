from __future__ import annotations

import argparse
from pathlib import Path

from build_image_manifest import DEFAULT_GALLERY_DIR, DEFAULT_SOURCE_DIR, build_manifest
from build_thumbnails import DEFAULT_MAX_EDGE, DEFAULT_QUALITY, build_thumbnails


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the extracted image gallery manifests and optional thumbnails."
    )
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Directory containing extracted image crops.",
    )
    parser.add_argument(
        "--gallery-dir",
        default=str(DEFAULT_GALLERY_DIR),
        help="Gallery directory that will receive manifests and thumbnails.",
    )
    parser.add_argument(
        "--skip-thumbnails",
        action="store_true",
        help="Only build JSON manifests.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Optional start year filter for thumbnails.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Optional end year filter for thumbnails.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional thumbnail limit for testing.",
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
        "--force",
        action="store_true",
        help="Regenerate thumbnails even when they already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    gallery_dir = Path(args.gallery_dir).resolve()

    manifest_summary = build_manifest(source_dir=source_dir, gallery_dir=gallery_dir)
    print("Manifest build complete")
    print("  Index: {}".format(manifest_summary["index_path"]))
    print("  Images indexed: {}".format(manifest_summary["total_images"]))

    if args.skip_thumbnails:
        return

    try:
        thumbnail_summary = build_thumbnails(
            source_dir=source_dir,
            gallery_dir=gallery_dir,
            start_year=args.start_year,
            end_year=args.end_year,
            limit=args.limit,
            max_edge=args.max_edge,
            quality=args.quality,
            force=args.force,
        )
    except RuntimeError as exc:
        print("Thumbnail build skipped: {}".format(exc))
        print("Install Pillow or rerun with --skip-thumbnails.")
        return

    print("Thumbnail build complete")
    print("  Built: {}".format(thumbnail_summary["processed"]))
    print("  Skipped: {}".format(thumbnail_summary["skipped"]))


if __name__ == "__main__":
    main()
