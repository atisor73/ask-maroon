import json
import os
from pathlib import Path
from typing import Iterable, Iterator, Optional


DEFAULT_R2_PREFIX = "archive"


def build_r2_client():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for R2 access.") from exc

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
        raise RuntimeError("botocore is required for R2 access.") from exc

    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def list_r2_keys(
    client,
    bucket: str,
    prefix: str,
    *,
    suffix: Optional[str] = None,
) -> Iterator[str]:
    continuation_token = None

    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = client.list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            key = item["Key"]
            if suffix is not None and not key.endswith(suffix):
                continue
            yield key

        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def download_r2_object(client, bucket: str, key: str, destination: Path) -> Path:
    ensure_parent(destination)
    client.download_file(bucket, key, str(destination))
    return destination


def read_r2_text(client, bucket: str, key: str, encoding: str = "utf-8") -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode(encoding)


def read_r2_jsonl(client, bucket: str, key: str) -> list[dict]:
    text = read_r2_text(client, bucket, key)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def upload_file_to_r2(
    client,
    bucket: str,
    local_path: Path,
    object_key: str,
    *,
    content_type: Optional[str] = None,
) -> None:
    extra_args = {}
    if content_type:
        extra_args["ExtraArgs"] = {"ContentType": content_type}

    client.upload_file(str(local_path), bucket, object_key, **extra_args)


def upload_jsonl_rows(client, bucket: str, object_key: str, rows: Iterable[dict]) -> None:
    body = "\n".join(json.dumps(row) for row in rows)
    client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=body.encode("utf-8"),
        ContentType="application/x-ndjson",
    )


def normalized_prefix(prefix: str) -> str:
    clean = prefix.strip("/")
    return f"{clean}/" if clean else ""
