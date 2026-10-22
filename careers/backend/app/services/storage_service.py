import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.services.s3_service import (
    delete_file_from_s3,
    generate_presigned_url,
    get_bytes_from_s3,
    get_text_from_s3,
    put_bytes_to_s3,
)

logger = logging.getLogger(__name__)


@dataclass
class StoredFile:
    file_name: str
    file_url: str
    s3_key: str


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    return cleaned or "upload"


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.backend = self.settings.STORAGE_BACKEND.lower()
        if self.backend not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")

    def _validate_extension(self, filename: str) -> None:
        extension = Path(filename).suffix.lower()
        if extension not in self.settings.allowed_upload_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {extension}",
            )

    async def read_validated_upload(self, upload: UploadFile) -> tuple[str, bytes]:
        original_name = _safe_filename(upload.filename or "upload")
        self._validate_extension(original_name)

        data = await upload.read()
        if len(data) > self.settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds {self.settings.MAX_UPLOAD_SIZE_MB} MB limit",
            )
        return original_name, data

    async def save_file(
        self,
        upload: UploadFile,
        user_id: int,
        application_id: int,
    ) -> StoredFile:
        original_name, data = await self.read_validated_upload(upload)

        key = f"user_{user_id}/application_{application_id}/{uuid.uuid4().hex}_{original_name}"

        if self.backend == "s3":
            return self._save_to_s3(key, original_name, data, upload.content_type)
        return self._save_local(key, original_name, data)

    def _save_local(self, key: str, original_name: str, data: bytes) -> StoredFile:
        upload_dir = Path(self.settings.LOCAL_UPLOAD_DIR)
        target = upload_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        logger.info("Saved local upload key=%s bytes=%s", key, len(data))
        return StoredFile(
            file_name=original_name,
            file_url=f"/uploads/{key}",
            s3_key=key,
        )

    def _save_to_s3(
        self,
        key: str,
        original_name: str,
        data: bytes,
        content_type: str | None,
    ) -> StoredFile:
        put_bytes_to_s3(key, data, content_type)
        file_url = f"s3://{self.settings.S3_BUCKET}/{key}"
        logger.info("Saved S3 upload key=%s bytes=%s", key, len(data))
        return StoredFile(file_name=original_name, file_url=file_url, s3_key=key)

    def delete_file(self, key: str) -> None:
        if self.backend == "s3":
            delete_file_from_s3(key)
            logger.info("Deleted S3 object key=%s", key)
            return

        target = Path(self.settings.LOCAL_UPLOAD_DIR) / key
        if target.exists():
            target.unlink()
            logger.info("Deleted local upload key=%s", key)

    def read_text_file(self, key: str) -> str:
        if self.backend == "s3":
            return get_text_from_s3(key)

        target = Path(self.settings.LOCAL_UPLOAD_DIR) / key
        if not target.exists():
            raise HTTPException(status_code=404, detail="Stored file not found")
        return target.read_text(encoding="utf-8", errors="replace")

    def read_file_bytes(self, key: str) -> bytes:
        if self.backend == "s3":
            return get_bytes_from_s3(key)

        target = Path(self.settings.LOCAL_UPLOAD_DIR) / key
        if not target.exists():
            raise HTTPException(status_code=404, detail="Stored file not found")
        return target.read_bytes()

    def generate_download_url(
        self, key: str, fallback_url: str | None = None, expires_in: int = 3600
    ) -> str:
        if self.backend == "s3":
            return str(generate_presigned_url(key, expires_in=expires_in))
        return fallback_url or f"/uploads/{key}"
