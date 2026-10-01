"""Storage bucket access through the S3 API (Supabase Storage in production).

The browser never sends audio through our API: we hand it a short-lived
presigned PUT URL and it uploads straight to the bucket. That is what lets a
file of any size through without hitting request-body limits on our server.
"""

from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings


@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        # Supabase serves buckets as a path (/bucket/key), not as a subdomain.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def presigned_put_url(key: str, content_type: str, expires_s: int = 3600) -> str:
    # The browser must send exactly this Content-Type, or the bucket rejects the signature.
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_s,
    )


def presigned_get_url(key: str, expires_s: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": settings.s3_bucket, "Key": key}, ExpiresIn=expires_s
    )


def object_size(key: str) -> int | None:
    """Size in bytes, or None if the object isn't in the bucket (upload never finished)."""
    try:
        return _client().head_object(Bucket=settings.s3_bucket, Key=key)["ContentLength"]
    except ClientError:
        return None


def download(key: str, dest: Path) -> None:
    _client().download_file(settings.s3_bucket, key, str(dest))


def delete(key: str) -> None:
    # S3 DeleteObject succeeds even if the key doesn't exist (e.g. an upload that never finished).
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)


def set_cors(origins: list[str]) -> None:
    """Let the browser PUT/GET from our frontend's origin (needed on R2/S3; Supabase allows all origins)."""
    _client().put_bucket_cors(
        Bucket=settings.s3_bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": origins,
                    "AllowedMethods": ["PUT", "GET", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        },
    )
