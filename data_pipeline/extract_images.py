"""
Extract image-like regions from archive PDFs using the Newspaper Navigator model.

This script renders PDF pages to raster images, runs a Detectron2-based layout
detector through LayoutParser, filters the detections down to image-bearing
classes such as photographs/maps/illustrations, and saves cropped image regions
plus JSONL metadata for downstream inspection.

Environment setup is expected to follow:
  conda env create -f data_pipeline/img_extractor.yml
  conda activate image-extractor
  python -m pip install --no-build-isolation 'git+https://github.com/facebookresearch/detectron2.git'

Default model weights are expected at:
  ~/newspaper_navigator_model/model_final.pth

Example:
  python extract_images.py --limit-pdfs 5 --page-limit 2
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional

import cv2
import numpy as np
from pdf2image import convert_from_path, pdfinfo_from_path
from tqdm import tqdm


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
PDF_ROOT = OUTPUT_DIR / "pdfs"
EXTRACTED_IMAGES_DIR = OUTPUT_DIR / "extracted_images"
DEFAULT_METADATA_PATH = OUTPUT_DIR / "metadata" / "image_regions.jsonl"

DEFAULT_MODEL_WEIGHTS = Path.home() / "newspaper_navigator_model" / "model_final.pth"
DEFAULT_CONFIG_PATH = "COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml"
DEFAULT_DPI = 144
DEFAULT_SCORE_THRESHOLD = 0.70
DEFAULT_PADDING = 8
DEFAULT_MIN_SIDE = 48

NEWSPAPER_NAVIGATOR_LABEL_MAP = {
    0: "Photograph",
    1: "Illustration",
    2: "Map",
    3: "Comics/Cartoon",
    4: "Editorial Cartoon",
    5: "Headline",
    6: "Advertisement",
}

DEFAULT_IMAGE_LABELS = {
    "photograph",
    "illustration",
    "map",
    "comics/cartoon",
    "editorial cartoon",
}


def resolve_detectron2_config_path(config_path: str) -> str:
    """
    Accept either a local config file or a Detectron2 model-zoo identifier.
    """

    expanded_path = Path(config_path).expanduser()
    if expanded_path.exists():
        return str(expanded_path)

    spec = importlib.util.find_spec("detectron2")
    package_paths = []
    if spec is not None:
        if spec.submodule_search_locations:
            package_paths.extend(Path(path) for path in spec.submodule_search_locations)
        elif spec.origin:
            package_paths.append(Path(spec.origin).resolve().parent)

    for package_path in package_paths:
        candidate_paths = [
            package_path / "model_zoo" / "configs" / config_path,
            package_path.parent / "configs" / config_path,
            package_path / "configs" / config_path,
        ]
        for candidate_path in candidate_paths:
            if candidate_path.exists():
                return str(candidate_path.resolve())

    try:
        from detectron2 import model_zoo  # type: ignore
    except Exception as exc:
        raise FileNotFoundError(
            "Config file '{}' was not found locally or inside the installed detectron2 package, and detectron2.model_zoo could not be imported.".format(
                config_path
            )
        ) from exc

    return model_zoo.get_config_file(config_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract image-like crops from archive PDFs.")
    parser.add_argument("--pdf-root", default=str(PDF_ROOT), help="Root directory containing archive PDFs.")
    parser.add_argument(
        "--output-dir",
        default=str(EXTRACTED_IMAGES_DIR),
        help="Directory where extracted image crops will be written.",
    )
    parser.add_argument(
        "--metadata-path",
        default=str(DEFAULT_METADATA_PATH),
        help="JSONL file to write extraction metadata into.",
    )
    parser.add_argument(
        "--weights-path",
        default=str(DEFAULT_MODEL_WEIGHTS),
        help="Path to Newspaper Navigator model weights (.pth).",
    )
    parser.add_argument(
        "--config-path",
        default=DEFAULT_CONFIG_PATH,
        help="Detectron2 config name/path used with the Newspaper Navigator weights.",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="PDF render resolution.")
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=DEFAULT_SCORE_THRESHOLD,
        help="Minimum detection score to keep.",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=DEFAULT_PADDING,
        help="Padding in pixels added around each crop.",
    )
    parser.add_argument(
        "--min-side",
        type=int,
        default=DEFAULT_MIN_SIDE,
        help="Minimum width/height in pixels for saved crops.",
    )
    parser.add_argument("--limit-pdfs", type=int, default=None, help="Optional PDF limit for testing.")
    parser.add_argument("--page-limit", type=int, default=None, help="Optional per-PDF page limit.")
    parser.add_argument(
        "--labels",
        nargs="+",
        default=sorted(DEFAULT_IMAGE_LABELS),
        help="Detection labels to keep. Defaults to image-bearing Newspaper Navigator classes.",
    )
    return parser.parse_args()


def find_pdfs(pdf_root: Path, limit: Optional[int] = None) -> List[Path]:
    pdf_paths = sorted(path for path in pdf_root.rglob("*.pdf") if path.is_file())
    return pdf_paths[:limit] if limit is not None else pdf_paths


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "region"


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def pil_to_bgr(image) -> np.ndarray:
    rgb_array = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)


def bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def load_newspaper_navigator_model(
    weights_path: Path = DEFAULT_MODEL_WEIGHTS,
    config_path: str = DEFAULT_CONFIG_PATH,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    label_map: Optional[dict] = None,
):
    """
    Build a LayoutParser Detectron2 model around the Newspaper Navigator weights.

    The weights path is project/user-specific and the Detectron2 config is kept as
    an argument because some environments may need to swap architectures.
    """

    try:
        import layoutparser as lp  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "layoutparser is required. Activate the image-extractor environment first."
        ) from exc

    weights_path = Path(weights_path).expanduser()
    if not weights_path.exists():
        raise FileNotFoundError(
            "Newspaper Navigator weights not found at {}. Run data_pipeline/img_setup.sh first.".format(
                weights_path
            )
        )

    label_map = label_map or NEWSPAPER_NAVIGATOR_LABEL_MAP
    resolved_config_path = resolve_detectron2_config_path(config_path)
    extra_config = [
        "MODEL.ROI_HEADS.SCORE_THRESH_TEST",
        float(score_threshold),
        "MODEL.ROI_HEADS.NUM_CLASSES",
        len(label_map),
    ]

    return lp.Detectron2LayoutModel(
        config_path=resolved_config_path,
        model_path=str(weights_path),
        extra_config=extra_config,
        label_map=label_map,
    )


def page_count_for_pdf(pdf_path: Path) -> int:
    info = pdfinfo_from_path(str(pdf_path))
    return int(info["Pages"])


def render_pdf_page(pdf_path: Path, page_number: int, dpi: int = DEFAULT_DPI) -> np.ndarray:
    images = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        first_page=page_number,
        last_page=page_number,
    )
    if not images:
        raise RuntimeError("Failed to render page {} from {}".format(page_number, pdf_path))
    return pil_to_bgr(images[0])


def detect_layout(model, page_image: np.ndarray):
    try:
        import layoutparser as lp  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "layoutparser is required. Activate the image-extractor environment first."
        ) from exc

    rgb_image = bgr_to_rgb(page_image)
    layout = model.detect(rgb_image)
    if layout is None:
        return lp.Layout([])
    return layout


def filter_layout_blocks(layout, labels_to_keep: Iterable[str], min_side: int) -> List[object]:
    normalized_labels = {label.lower() for label in labels_to_keep}
    kept = []

    for block in layout:
        label = str(getattr(block, "type", "") or "").lower()
        if label not in normalized_labels:
            continue

        x1, y1, x2, y2 = block_coordinates(block)
        if (x2 - x1) < min_side or (y2 - y1) < min_side:
            continue
        kept.append(block)

    return kept


def block_coordinates(block) -> tuple[int, int, int, int]:
    x1 = int(round(block.block.x_1))
    y1 = int(round(block.block.y_1))
    x2 = int(round(block.block.x_2))
    y2 = int(round(block.block.y_2))
    return x1, y1, x2, y2


def crop_block(page_image: np.ndarray, block, padding: int = DEFAULT_PADDING) -> tuple[np.ndarray, dict]:
    height, width = page_image.shape[:2]
    x1, y1, x2, y2 = block_coordinates(block)
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(width, x2 + padding)
    y2 = min(height, y2 + padding)
    crop = page_image[y1:y2, x1:x2]
    box = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": x2 - x1, "height": y2 - y1}
    return crop, box


def crop_output_path(output_dir: Path, pdf_root: Path, pdf_path: Path, page_number: int, region_index: int, label: str) -> Path:
    relative_parent = pdf_path.relative_to(pdf_root).parent
    filename = "{}_page-{:04d}_region-{:03d}_{}.png".format(
        pdf_path.stem,
        page_number,
        region_index,
        slugify(label),
    )
    return output_dir / relative_parent / pdf_path.stem / filename


def draw_detection_preview(page_image: np.ndarray, blocks: Iterable[object]) -> np.ndarray:
    preview = page_image.copy()
    for block in blocks:
        x1, y1, x2, y2 = block_coordinates(block)
        score = float(getattr(block, "score", 0.0) or 0.0)
        label = str(getattr(block, "type", "") or "Region")
        cv2.rectangle(preview, (x1, y1), (x2, y2), (109, 16, 34), 2)
        text = "{} {:.2f}".format(label, score)
        cv2.putText(
            preview,
            text,
            (x1, max(24, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (109, 16, 34),
            2,
            cv2.LINE_AA,
        )
    return preview


def extract_images_from_pdf(
    pdf_path: Path,
    model,
    pdf_root: Path,
    output_dir: Path,
    labels_to_keep: Iterable[str],
    dpi: int = DEFAULT_DPI,
    page_limit: Optional[int] = None,
    padding: int = DEFAULT_PADDING,
    min_side: int = DEFAULT_MIN_SIDE,
) -> List[dict]:
    results: List[dict] = []
    max_pages = page_count_for_pdf(pdf_path)
    if page_limit is not None:
        max_pages = min(max_pages, page_limit)

    for page_number in range(1, max_pages + 1):
        page_image = render_pdf_page(pdf_path=pdf_path, page_number=page_number, dpi=dpi)
        layout = detect_layout(model=model, page_image=page_image)
        blocks = filter_layout_blocks(layout=layout, labels_to_keep=labels_to_keep, min_side=min_side)

        for region_index, block in enumerate(blocks, start=1):
            crop, box = crop_block(page_image=page_image, block=block, padding=padding)
            label = str(getattr(block, "type", "") or "region")
            score = float(getattr(block, "score", 0.0) or 0.0)
            crop_path = crop_output_path(
                output_dir=output_dir,
                pdf_root=pdf_root,
                pdf_path=pdf_path,
                page_number=page_number,
                region_index=region_index,
                label=label,
            )
            ensure_parent_dir(crop_path)
            if crop.size == 0:
                continue
            cv2.imwrite(str(crop_path), crop)
            results.append(
                {
                    "doc_id": pdf_path.stem,
                    "pdf_path": str(pdf_path),
                    "pdf_relative_path": str(pdf_path.relative_to(pdf_root)),
                    "page_number": page_number,
                    "region_index": region_index,
                    "label": label,
                    "label_slug": slugify(label),
                    "score": score,
                    "crop_path": str(crop_path),
                    "box": box,
                }
            )

    return results


def write_metadata(rows: Iterable[dict], metadata_path: Path) -> None:
    ensure_parent_dir(metadata_path)
    with metadata_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def summarize_by_label(rows: Iterable[dict]) -> Counter:
    counter = Counter()
    for row in rows:
        counter[row["label"]] += 1
    return counter


def main() -> None:
    args = parse_args()
    pdf_root = Path(args.pdf_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    metadata_path = Path(args.metadata_path).resolve()
    labels_to_keep = [label.lower() for label in args.labels]

    pdf_paths = find_pdfs(pdf_root=pdf_root, limit=args.limit_pdfs)
    if not pdf_paths:
        raise FileNotFoundError("No PDFs found under {}".format(pdf_root))

    print("Loading Newspaper Navigator model...")
    model = load_newspaper_navigator_model(
        weights_path=Path(args.weights_path),
        config_path=args.config_path,
        score_threshold=args.score_threshold,
    )

    all_rows: List[dict] = []
    for pdf_path in tqdm(pdf_paths, desc="Extracting image regions", unit="pdf"):
        all_rows.extend(
            extract_images_from_pdf(
                pdf_path=pdf_path,
                model=model,
                pdf_root=pdf_root,
                output_dir=output_dir,
                labels_to_keep=labels_to_keep,
                dpi=args.dpi,
                page_limit=args.page_limit,
                padding=args.padding,
                min_side=args.min_side,
            )
        )

    write_metadata(rows=all_rows, metadata_path=metadata_path)

    summary = summarize_by_label(all_rows)
    print("Saved {} extracted crops".format(len(all_rows)))
    print("Metadata: {}".format(metadata_path))
    for label, count in summary.most_common():
        print("  {}: {}".format(label, count))


if __name__ == "__main__":
    main()
