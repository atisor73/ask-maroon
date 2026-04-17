import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
from tqdm import tqdm


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DEFAULT_MAX_WORKERS = 8
DEFAULT_R2_PREFIX = "archive"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload every file under output/ to Cloudflare R2."
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Local directory to upload recursively.",
    )
    parser.add_argument(
        "--r2-prefix",
        default=DEFAULT_R2_PREFIX,
        help="Object key prefix inside the target bucket, e.g. 'archive' for s3://<bucket>/archive/...",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Number of concurrent uploads.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite R2 objects even if they already exist.",
    )
    parser.add_argument(
        "--print-r2-logs",
        action="store_true",
        help="Print upload and skip events using tqdm.write.",
    )
    return parser.parse_args()


def build_r2_client():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for R2 uploads.") from exc

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
        raise RuntimeError("botocore is required for R2 uploads.") from exc

    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def make_object_key(root: Path, file_path: Path, prefix: str) -> str:
    relative = file_path.relative_to(root).as_posix()
    normalized_prefix = prefix.strip("/")
    return f"{normalized_prefix}/{relative}" if normalized_prefix else relative


def log_r2_event(enabled: bool, message: str) -> None:
    if enabled:
        tqdm.write(message)


def upload_one(
    client,
    bucket: str,
    root: Path,
    file_path: Path,
    prefix: str,
    *,
    force: bool,
    print_r2_logs: bool,
) -> dict:
    object_key = make_object_key(root, file_path, prefix)

    if not force and object_exists_r2(client, bucket, object_key):
        log_r2_event(print_r2_logs, f"[R2 SKIP] s3://{bucket}/{object_key}")
        return {"status": "skipped", "path": str(file_path), "r2_key": object_key}

    client.upload_file(str(file_path), bucket, object_key)
    log_r2_event(print_r2_logs, f"[R2 UPLOAD] s3://{bucket}/{object_key}")
    return {"status": "uploaded", "path": str(file_path), "r2_key": object_key}


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    output_dir = Path(args.output_dir).resolve()
    if not output_dir.exists():
        raise RuntimeError(f"Output directory does not exist: {output_dir}")
    if not output_dir.is_dir():
        raise RuntimeError(f"Output path is not a directory: {output_dir}")

    files: List[Path] = list(iter_files(output_dir))
    client, bucket = build_r2_client()

    uploaded = 0
    skipped = 0
    failed = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(
                upload_one,
                client,
                bucket,
                output_dir,
                file_path,
                args.r2_prefix,
                force=args.force,
                print_r2_logs=args.print_r2_logs,
            )
            for file_path in files
        ]

        for future in tqdm(futures, total=len(futures), desc="Uploading output/ to R2", unit="file"):
            try:
                result = future.result()
            except Exception as exc:
                failed.append(str(exc))
                continue

            if result["status"] == "uploaded":
                uploaded += 1
            else:
                skipped += 1

    print(f"Bucket: {bucket}")
    print(f"Prefix: {args.r2_prefix}")
    print(f"Local root: {output_dir}")
    print(f"Files discovered: {len(files)}")
    print(f"Uploaded: {uploaded}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {len(failed)}")

    if failed:
        print("First failure:", failed[0])


if __name__ == "__main__":
    main()
