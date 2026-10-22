import re
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from fastapi import HTTPException, status

from app.core.config import get_settings


def _s3_client():
    settings = get_settings()
    endpoint_url = settings.S3_ENDPOINT_URL.strip() if settings.S3_ENDPOINT_URL else None
    kwargs = {
        "region_name": settings.AWS_REGION,
        "endpoint_url": endpoint_url or None,
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        ),
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
    return boto3.client("s3", **kwargs)


def _bucket_name() -> str:
    bucket = get_settings().S3_BUCKET
    if not bucket:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3_BUCKET is not configured",
        )
    return bucket


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    return cleaned or "upload"


def upload_file_to_s3(file_obj, user_id: str, filename: str, content_type: str | None):
    file_key = f"users/{user_id}/documents/{uuid.uuid4()}-{_safe_filename(filename)}"
    _s3_client().upload_fileobj(
        file_obj,
        _bucket_name(),
        file_key,
        ExtraArgs={"ContentType": content_type or "application/octet-stream"},
    )
    return file_key


def put_bytes_to_s3(file_key: str, data: bytes, content_type: str | None):
    _s3_client().put_object(
        Bucket=_bucket_name(),
        Key=file_key,
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )
    return file_key


def generate_presigned_url(file_key: str, expires_in: int = 3600):
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket_name(), "Key": file_key},
        ExpiresIn=expires_in,
    )


def delete_file_from_s3(file_key: str):
    _s3_client().delete_object(Bucket=_bucket_name(), Key=file_key)


def get_text_from_s3(file_key: str) -> str:
    obj = _s3_client().get_object(Bucket=_bucket_name(), Key=file_key)
    return str(obj["Body"].read().decode("utf-8", errors="replace"))


def get_bytes_from_s3(file_key: str) -> bytes:
    obj = _s3_client().get_object(Bucket=_bucket_name(), Key=file_key)
    return obj["Body"].read()
