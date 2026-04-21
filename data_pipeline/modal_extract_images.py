"""
Modal runner for distributed image extraction from archive PDFs stored in R2.

Workflow:
1. List PDF object keys from Cloudflare R2.
2. Fan out PDF batches to Modal workers.
3. Each worker downloads PDFs to /tmp, extracts image regions with
   Newspaper Navigator, and uploads crops + per-document metadata back to R2.

Example:
  modal run data_pipeline/modal_extract_images.py --limit 100 --batch-size 4
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Iterator, List

import modal
from dotenv import load_dotenv

try:
    from data_pipeline.extract_images import (
        DEFAULT_DPI,
        DEFAULT_MIN_SIDE,
        DEFAULT_PADDING,
        DEFAULT_SCORE_THRESHOLD,
        EXTRACTED_IMAGES_DIR,
        extract_images_from_pdf,
        load_newspaper_navigator_model,
        write_metadata,
    )
    from data_pipeline.r2_utils import (
        DEFAULT_R2_PREFIX,
        build_r2_client,
        download_r2_object,
        list_r2_keys,
        normalized_prefix,
        object_exists_r2,
        upload_file_to_r2,
    )
except ModuleNotFoundError:
    from extract_images import (
        DEFAULT_DPI,
        DEFAULT_MIN_SIDE,
        DEFAULT_PADDING,
        DEFAULT_SCORE_THRESHOLD,
        EXTRACTED_IMAGES_DIR,
        extract_images_from_pdf,
        load_newspaper_navigator_model,
        write_metadata,
    )
    from r2_utils import (
        DEFAULT_R2_PREFIX,
        build_r2_client,
        download_r2_object,
        list_r2_keys,
        normalized_prefix,
        object_exists_r2,
        upload_file_to_r2,
    )


APP_NAME = "maroon-image-extractor"
R2_SECRET_NAME = os.getenv("MODAL_R2_SECRET_NAME", "cloudflare-r2")
DEFAULT_PDF_SUBPREFIX = "pdfs/"
DEFAULT_OUTPUT_SUBPREFIX = "extracted_images/"
DEFAULT_CPU = 4
DEFAULT_MEMORY_MB = 8192
DEFAULT_TIMEOUT_SECONDS = 60 * 60
DEFAULT_BATCH_SIZE = 4
DEFAULT_MODEL_WEIGHTS = "/models/newspaper_navigator/model_final.pth"
DEFAULT_GPU_TYPE = "T4"

IMAGE_LABELS = [
    "Photograph",
    "Illustration",
    "Map",
    "Comics/Cartoon",
    "Editorial Cartoon",
]

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.10")
    .add_local_dir(Path(__file__).resolve().parent, remote_path="/root", copy=True)
    .apt_install(
        "git",
        "wget",
        "build-essential",
        "poppler-utils",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxrender1",
        "libxext6",
    )
    .pip_install(
        "boto3",
        "numpy",
        "opencv-python-headless",
        "pdf2image",
        "tqdm",
        "layoutparser",
        "python-dotenv",
        "Pillow",
        "torch",
        "torchvision",
    )
    .run_commands(
        "python -m pip install --no-build-isolation 'git+https://github.com/facebookresearch/detectron2.git'",
        "mkdir -p /models/newspaper_navigator",
        "wget -O /models/newspaper_navigator/model_final.pth "
        "'https://github.com/LibraryOfCongress/newspaper-navigator/releases/download/v1.0.0/model_final.pth'",
    )
)

_MODEL = None


def chunked(items: List[str], batch_size: int) -> Iterator[List[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def parse_pdf_r2_key(pdf_key: str, r2_prefix: str) -> dict:
    prefix = normalized_prefix(r2_prefix)
    relative_key = pdf_key[len(prefix) :] if prefix and pdf_key.startswith(prefix) else pdf_key
    parts = relative_key.split("/")
    if len(parts) < 4 or parts[0] != "pdfs":
        raise ValueError("Unexpected PDF key format: {}".format(pdf_key))

    year, month, filename = parts[1], parts[2], parts[3]
    doc_id = Path(filename).stem
    return {
        "pdf_key": pdf_key,
        "relative_key": relative_key,
        "year": year,
        "month": month,
        "doc_id": doc_id,
    }


def doc_output_prefix(doc_info: dict, r2_prefix: str) -> str:
    prefix = normalized_prefix(r2_prefix)
    return "{}extracted_images/{}/{}/{}/".format(prefix, doc_info["year"], doc_info["month"], doc_info["doc_id"])


def doc_metadata_key(doc_info: dict, r2_prefix: str) -> str:
    return "{}regions.jsonl".format(doc_output_prefix(doc_info, r2_prefix))


def local_pdf_path(temp_root: Path, doc_info: dict) -> Path:
    return temp_root / "pdfs" / doc_info["year"] / doc_info["month"] / "{}.pdf".format(doc_info["doc_id"])


def local_output_dir(temp_root: Path) -> Path:
    return temp_root / EXTRACTED_IMAGES_DIR.name


def metadata_row_with_r2_keys(row: dict, output_root: Path, r2_prefix: str) -> dict:
    relative_crop_path = Path(row["crop_path"]).relative_to(output_root).as_posix()
    crop_key = "{}{}{}".format(normalized_prefix(r2_prefix), DEFAULT_OUTPUT_SUBPREFIX, relative_crop_path)
    return {
        **row,
        "r2_crop_key": crop_key,
    }


def get_model(weights_path: str = DEFAULT_MODEL_WEIGHTS, score_threshold: float = DEFAULT_SCORE_THRESHOLD):
    global _MODEL
    if _MODEL is None:
        _MODEL = load_newspaper_navigator_model(
            weights_path=Path(weights_path),
            score_threshold=score_threshold,
        )
    return _MODEL


def detect_runtime_device() -> str:
    try:
        import torch
    except Exception:
        return "CPU (torch unavailable)"

    if torch.cuda.is_available():
        try:
            return "GPU ({})".format(torch.cuda.get_device_name(0))
        except Exception:
            return "GPU (cuda available)"

    return "CPU"


def process_pdf_batch_impl(request: dict, execution_mode: str) -> List[dict]:
    runtime_device = detect_runtime_device()
    print("[{} worker] runtime device: {}".format(execution_mode, runtime_device))

    client, bucket = build_r2_client()
    model = get_model(
        weights_path=request.get("weights_path", DEFAULT_MODEL_WEIGHTS),
        score_threshold=request.get("score_threshold", DEFAULT_SCORE_THRESHOLD),
    )

    temp_root = Path(tempfile.mkdtemp(prefix="maroon-image-extract-"))
    results: List[dict] = []

    try:
        output_root = local_output_dir(temp_root)

        for pdf_key in request["pdf_keys"]:
            doc_info = parse_pdf_r2_key(pdf_key, request["r2_prefix"])
            metadata_key = doc_metadata_key(doc_info, request["r2_prefix"])

            if not request.get("force", False) and object_exists_r2(client, bucket, metadata_key):
                results.append(
                    {
                        "pdf_key": pdf_key,
                        "doc_id": doc_info["doc_id"],
                        "status": "skipped",
                        "metadata_key": metadata_key,
                        "execution_mode": execution_mode,
                        "runtime_device": runtime_device,
                    }
                )
                continue

            pdf_path = local_pdf_path(temp_root, doc_info)
            download_r2_object(client, bucket, pdf_key, pdf_path)

            try:
                rows = extract_images_from_pdf(
                    pdf_path=pdf_path,
                    model=model,
                    pdf_root=temp_root / "pdfs",
                    output_dir=output_root,
                    labels_to_keep=request.get("labels", IMAGE_LABELS),
                    dpi=request.get("dpi", DEFAULT_DPI),
                    page_limit=request.get("page_limit"),
                    padding=request.get("padding", DEFAULT_PADDING),
                    min_side=request.get("min_side", DEFAULT_MIN_SIDE),
                )
            except Exception as exc:
                print(
                    "[{} worker] failed to process {}: {}".format(
                        execution_mode,
                        pdf_key,
                        exc,
                    )
                )
                results.append(
                    {
                        "pdf_key": pdf_key,
                        "doc_id": doc_info["doc_id"],
                        "status": "failed",
                        "error": str(exc),
                        "metadata_key": metadata_key,
                        "execution_mode": execution_mode,
                        "runtime_device": runtime_device,
                    }
                )
                continue

            rows_with_r2 = [
                metadata_row_with_r2_keys(row=row, output_root=output_root, r2_prefix=request["r2_prefix"])
                for row in rows
            ]

            for row in rows_with_r2:
                crop_path = Path(row["crop_path"])
                relative_crop_path = crop_path.relative_to(output_root).as_posix()
                crop_key = "{}{}{}".format(
                    normalized_prefix(request["r2_prefix"]),
                    DEFAULT_OUTPUT_SUBPREFIX,
                    relative_crop_path,
                )
                upload_file_to_r2(
                    client,
                    bucket,
                    crop_path,
                    crop_key,
                    content_type="image/png",
                )

            metadata_local_path = output_root / doc_info["year"] / doc_info["month"] / doc_info["doc_id"] / "regions.jsonl"
            write_metadata(rows_with_r2, metadata_local_path)
            upload_file_to_r2(
                client,
                bucket,
                metadata_local_path,
                metadata_key,
                content_type="application/x-ndjson",
            )

            results.append(
                {
                    "pdf_key": pdf_key,
                    "doc_id": doc_info["doc_id"],
                    "status": "processed",
                    "num_regions": len(rows_with_r2),
                    "metadata_key": metadata_key,
                    "execution_mode": execution_mode,
                    "runtime_device": runtime_device,
                }
            )

        return results
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@app.function(
    image=image,
    cpu=DEFAULT_CPU,
    memory=DEFAULT_MEMORY_MB,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    secrets=[modal.Secret.from_name(R2_SECRET_NAME)],
)
def process_pdf_batch_cpu(request: dict) -> List[dict]:
    return process_pdf_batch_impl(request, execution_mode="cpu")


@app.function(
    image=image,
    cpu=DEFAULT_CPU,
    memory=DEFAULT_MEMORY_MB,
    gpu=DEFAULT_GPU_TYPE,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    secrets=[modal.Secret.from_name(R2_SECRET_NAME)],
)
def process_pdf_batch_gpu(request: dict) -> List[dict]:
    return process_pdf_batch_impl(request, execution_mode="gpu")


@app.local_entrypoint()
def main(
    limit: int = 0,
    batch_size: int = DEFAULT_BATCH_SIZE,
    r2_prefix: str = DEFAULT_R2_PREFIX,
    page_limit: int = 0,
    dpi: int = DEFAULT_DPI,
    force: bool = False,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    padding: int = DEFAULT_PADDING,
    min_side: int = DEFAULT_MIN_SIDE,
    use_gpu: bool = True,
):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    client, bucket = build_r2_client()
    pdf_prefix = "{}{}".format(normalized_prefix(r2_prefix), DEFAULT_PDF_SUBPREFIX)
    pdf_keys = list(list_r2_keys(client, bucket, pdf_prefix, suffix=".pdf"))
    if limit > 0:
        pdf_keys = pdf_keys[:limit]

    print("Bucket:", bucket)
    print("Prefix:", r2_prefix)
    print("PDFs queued:", len(pdf_keys))
    print("Batch size:", batch_size)
    print("Execution mode:", "gpu" if use_gpu else "cpu")

    requests = [
        {
            "pdf_keys": batch,
            "r2_prefix": r2_prefix,
            "page_limit": page_limit or None,
            "dpi": dpi,
            "force": force,
            "score_threshold": score_threshold,
            "padding": padding,
            "min_side": min_side,
            "labels": IMAGE_LABELS,
            "weights_path": DEFAULT_MODEL_WEIGHTS,
        }
        for batch in chunked(pdf_keys, batch_size)
    ]

    processed = 0
    skipped = 0
    failed = 0
    total_regions = 0

    worker = process_pdf_batch_gpu if use_gpu else process_pdf_batch_cpu

    for batch_result in worker.map(requests):
        for item in batch_result:
            if item["status"] == "processed":
                processed += 1
                total_regions += int(item.get("num_regions", 0))
            elif item["status"] == "skipped":
                skipped += 1
            elif item["status"] == "failed":
                failed += 1

            print(
                "Doc {} -> {} on {}".format(
                    item.get("doc_id"),
                    item.get("execution_mode", "unknown"),
                    item.get("runtime_device", "unknown"),
                )
            )
            if item.get("status") == "failed":
                print("  Failure:", item.get("error", "unknown error"))

    print("Processed PDFs:", processed)
    print("Skipped PDFs:", skipped)
    print("Failed PDFs:", failed)
    print("Extracted regions:", total_regions)
