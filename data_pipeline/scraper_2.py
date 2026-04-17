import argparse
import json
import os
import random
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DOCUMENTS_PATH = OUTPUT_DIR / "documents.json"
FAILED_DOWNLOADS_PATH = ROOT / "failed_downloads.json"

LOCAL_PDF_DIR = OUTPUT_DIR / "pdfs"
LOCAL_TEXT_DIR = OUTPUT_DIR / "plain_text"

DEFAULT_MODE = "local"
DEFAULT_MAX_WORKERS = 5
DEFAULT_R2_PREFIX = "archive"
DEFAULT_TEMP_DIR = Path(tempfile.gettempdir()) / "maroon-r2-cache"
DEFAULT_TIMEOUT = 15
DEFAULT_MAX_RETRIES = 5
DEFAULT_VERIFY_RETRIES = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download archive PDFs/plain text either to local disk or to Cloudflare R2."
    )
    parser.add_argument(
        "--mode",
        choices=["local", "r2"],
        default=DEFAULT_MODE,
        help="Where downloaded files should be written.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Number of concurrent document downloads.",
    )
    parser.add_argument(
        "--r2-prefix",
        default=DEFAULT_R2_PREFIX,
        help="Object key prefix inside the target bucket, e.g. 'archive' for s3://<bucket>/archive/...",
    )
    parser.add_argument(
        "--temp-dir",
        default=str(DEFAULT_TEMP_DIR),
        help="Temporary directory used for staged downloads before R2 upload.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite local files or R2 objects even if they already exist.",
    )
    parser.add_argument(
        "--print-r2-logs",
        action="store_true",
        help="Print R2 upload/skip logs using tqdm.write.",
    )
    return parser.parse_args()


def get_local_paths(doc: dict) -> Tuple[Path, Path]:
    doc_id = doc["id"]
    year = doc["year"]
    month = doc["month"]

    pdf_path = LOCAL_PDF_DIR / year / month / f"{doc_id}.pdf"
    text_path = LOCAL_TEXT_DIR / year / month / f"{doc_id}.txt"
    return pdf_path, text_path


def get_r2_keys(doc: dict, prefix: str) -> Tuple[str, str]:
    doc_id = doc["id"]
    year = doc["year"]
    month = doc["month"]
    normalized_prefix = prefix.strip("/")
    key_prefix = f"{normalized_prefix}/" if normalized_prefix else ""
    pdf_key = f"{key_prefix}pdfs/{year}/{month}/{doc_id}.pdf"
    text_key = f"{key_prefix}plain_text/{year}/{month}/{doc_id}.txt"
    return pdf_key, text_key


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_r2_client():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for --mode r2.") from exc

    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    missing = [
        name
        for name, value in (
            ("R2_ACCOUNT_ID", account_id),
            ("R2_ACCESS_KEY_ID", access_key),
            ("R2_SECRET_ACCESS_KEY", secret_key),
            ("R2_BUCKET", bucket),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Missing required R2 environment variables: {}".format(", ".join(missing)))

    endpoint_url = os.getenv("R2_ENDPOINT_URL") or f"https://{account_id}.r2.cloudflarestorage.com"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    return client, bucket


def object_exists_r2(client, bucket: str, key: str) -> bool:
    try:
        from botocore.exceptions import ClientError
    except Exception as exc:
        raise RuntimeError("botocore is required for --mode r2.") from exc

    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def request_with_retries(
    url: str,
    *,
    stream: bool,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, stream=stream, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception:
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"[RETRY] Attempt {attempt + 1} for {url} in {wait:.1f}s")
            time.sleep(wait)
    return None


def download_pdf_to_path(url: str, path: Path, overwrite: bool = False) -> bool:
    if path.exists() and not overwrite:
        return True

    ensure_parent(path)
    response = request_with_retries(url, stream=True)
    if response is None:
        print("[PDF FAILED]:", url)
        return False

    with response:
        with path.open("wb") as handle:
            for chunk in response.iter_content(8192):
                if chunk:
                    handle.write(chunk)
    return True


def download_text_to_path(url: str, path: Path, overwrite: bool = False) -> bool:
    if path.exists() and not overwrite:
        return True

    ensure_parent(path)
    response = request_with_retries(url, stream=False)
    if response is None:
        print("[TEXT FAILED]:", url)
        return False

    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text_clean = "\n".join(line for line in lines if line)

    path.write_text(text_clean, encoding="utf-8")
    return True


def upload_file_to_r2(client, bucket: str, local_path: Path, object_key: str) -> None:
    client.upload_file(str(local_path), bucket, object_key)


def log_r2_event(enabled: bool, message: str) -> None:
    if enabled:
        tqdm.write(message)


def verify_object_exists_r2(
    client,
    bucket: str,
    object_key: str,
    *,
    max_retries: int = DEFAULT_VERIFY_RETRIES,
) -> bool:
    for attempt in range(max_retries):
        if object_exists_r2(client, bucket, object_key):
            return True
        time.sleep(0.5 * (attempt + 1))
    return False


def download_and_upload_pdf(
    client,
    bucket: str,
    url: str,
    object_key: str,
    temp_dir: Path,
    overwrite: bool = False,
    print_r2_logs: bool = False,
) -> bool:
    if not overwrite and object_exists_r2(client, bucket, object_key):
        log_r2_event(print_r2_logs, f"[R2 SKIP PDF] s3://{bucket}/{object_key}")
        return True

    ensure_parent(temp_dir / "placeholder")
    temp_path = temp_dir / object_key
    try:
        if not download_pdf_to_path(url, temp_path, overwrite=True):
            return False
        upload_file_to_r2(client, bucket, temp_path, object_key)
        if not verify_object_exists_r2(client, bucket, object_key):
            log_r2_event(print_r2_logs, f"[R2 VERIFY FAILED PDF] s3://{bucket}/{object_key}")
            return False
        log_r2_event(print_r2_logs, f"[R2 UPLOAD PDF] s3://{bucket}/{object_key}")
        return True
    finally:
        if temp_path.exists():
            temp_path.unlink()


def download_and_upload_text(
    client,
    bucket: str,
    url: str,
    object_key: str,
    temp_dir: Path,
    local_path: Path,
    overwrite: bool = False,
    print_r2_logs: bool = False,
) -> bool:
    ensure_parent(temp_dir / "placeholder")
    ensure_parent(local_path)
    temp_path = temp_dir / object_key
    needs_upload = overwrite or not object_exists_r2(client, bucket, object_key)
    needs_local = overwrite or not local_path.exists()

    if not needs_upload and not needs_local:
        log_r2_event(print_r2_logs, f"[R2 SKIP TEXT] s3://{bucket}/{object_key}")
        return True

    try:
        if not download_text_to_path(url, temp_path, overwrite=True):
            return False

        if needs_upload:
            upload_file_to_r2(client, bucket, temp_path, object_key)
            if not verify_object_exists_r2(client, bucket, object_key):
                log_r2_event(print_r2_logs, f"[R2 VERIFY FAILED TEXT] s3://{bucket}/{object_key}")
                return False
            log_r2_event(print_r2_logs, f"[R2 UPLOAD TEXT] s3://{bucket}/{object_key}")
        else:
            log_r2_event(print_r2_logs, f"[R2 SKIP TEXT] s3://{bucket}/{object_key}")

        if needs_local:
            shutil.copyfile(temp_path, local_path)
        return True
    finally:
        if temp_path.exists():
            temp_path.unlink()


def count_files(root: Path, ext: str) -> int:
    if not root.exists():
        return 0
    total = 0
    for _, _, filenames in os.walk(root):
        total += sum(1 for name in filenames if name.endswith(ext))
    return total


class Downloader:
    def __init__(
        self,
        mode: str,
        *,
        force: bool,
        r2_prefix: str,
        temp_dir: Path,
        print_r2_logs: bool,
    ) -> None:
        self.mode = mode
        self.force = force
        self.r2_prefix = r2_prefix
        self.temp_dir = temp_dir
        self.print_r2_logs = print_r2_logs
        self.client = None
        self.bucket = None

        if self.mode == "r2":
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            self.client, self.bucket = build_r2_client()
        else:
            LOCAL_PDF_DIR.mkdir(parents=True, exist_ok=True)
            LOCAL_TEXT_DIR.mkdir(parents=True, exist_ok=True)

    def process_doc(self, doc: dict) -> List[dict]:
        results = []

        if self.mode == "local":
            pdf_path, text_path = get_local_paths(doc)
            if not download_pdf_to_path(doc["pdf_url"], pdf_path, overwrite=self.force):
                results.append({"type": "pdf", "url": doc["pdf_url"], "doc_id": doc["id"]})
            if not download_text_to_path(doc["plain_text_url"], text_path, overwrite=self.force):
                results.append({"type": "text", "url": doc["plain_text_url"], "doc_id": doc["id"]})
            return results

        pdf_key, text_key = get_r2_keys(doc, self.r2_prefix)
        _, local_text_path = get_local_paths(doc)
        if not download_and_upload_pdf(
            self.client,
            self.bucket,
            doc["pdf_url"],
            pdf_key,
            self.temp_dir,
            overwrite=self.force,
            print_r2_logs=self.print_r2_logs,
        ):
            results.append({"type": "pdf", "url": doc["pdf_url"], "doc_id": doc["id"], "r2_key": pdf_key})
        if not download_and_upload_text(
            self.client,
            self.bucket,
            doc["plain_text_url"],
            text_key,
            self.temp_dir,
            local_text_path,
            overwrite=self.force,
            print_r2_logs=self.print_r2_logs,
        ):
            results.append({"type": "text", "url": doc["plain_text_url"], "doc_id": doc["id"], "r2_key": text_key})
        return results


def load_documents(path: Path) -> List[Dict]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    docs = load_documents(DOCUMENTS_PATH)
    downloader = Downloader(
        args.mode,
        force=args.force,
        r2_prefix=args.r2_prefix,
        temp_dir=Path(args.temp_dir),
        print_r2_logs=args.print_r2_logs,
    )

    failed = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        for result in tqdm(executor.map(downloader.process_doc, docs), total=len(docs)):
            failed.extend(result)

    with FAILED_DOWNLOADS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(failed, handle, indent=2)

    print(f"Expected total docs: {len(docs)}")
    if args.mode == "local":
        num_pdfs = count_files(LOCAL_PDF_DIR, ".pdf")
        num_texts = count_files(LOCAL_TEXT_DIR, ".txt")
        print(f"Total on disk: {num_pdfs} PDFs and {num_texts} text files.")
    else:
        print(f"Upload mode: r2 (bucket={downloader.bucket}, prefix={args.r2_prefix})")
        print(f"Temporary cache dir: {Path(args.temp_dir)}")
        print("Existing R2 objects are skipped unless --force is passed.")


if __name__ == "__main__":
    main()
