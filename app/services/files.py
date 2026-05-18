"""Receipt file handling: validation, storage, deletion.

Keeps DB rows and disk files in sync. The DB is the source of truth:
on delete we commit the row removal first, then best-effort unlink the
file (logging, never raising, if the unlink fails).
"""

import logging
import uuid
from pathlib import Path

import aiofiles
import filetype
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.receipt import Receipt

logger = logging.getLogger("udlaeg.files")
settings = get_settings()

# Map validated MIME type -> canonical extension.
ALLOWED_MIME_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
    "image/heic": "heic",
}


def get_receipt_path(receipt: Receipt) -> Path:
    """Absolute path on disk for a stored receipt."""
    return Path(receipt.file_path)


async def save_receipt(session: AsyncSession, expense_id: int, upload: UploadFile) -> Receipt:
    """Validate and persist an uploaded receipt for an expense."""
    content = await upload.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tom fil")
    if size > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Filen er for stor (maks {settings.max_upload_mb} MB)",
        )

    kind = filetype.guess(content)
    mime = kind.mime if kind else None
    if mime not in ALLOWED_MIME_EXT:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Filtype ikke tilladt. Brug jpg, png, pdf eller heic.",
        )

    ext = ALLOWED_MIME_EXT[mime]
    target_dir = settings.receipts_dir / str(expense_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid.uuid4().hex}.{ext}"

    async with aiofiles.open(target_path, "wb") as fh:
        await fh.write(content)

    receipt = Receipt(
        expense_id=expense_id,
        file_path=str(target_path),
        mime_type=mime,
        file_size=size,
    )
    session.add(receipt)
    try:
        await session.commit()
    except Exception:
        # DB write failed -> remove the orphan file we just wrote.
        target_path.unlink(missing_ok=True)
        raise
    await session.refresh(receipt)
    logger.info(
        "file.upload",
        extra={"expense_id": expense_id, "receipt_id": receipt.id, "size": size},
    )
    return receipt


async def delete_receipt(session: AsyncSession, receipt: Receipt) -> None:
    """Delete a receipt row, then best-effort remove its file."""
    path = get_receipt_path(receipt)
    receipt_id = receipt.id
    expense_id = receipt.expense_id
    await session.delete(receipt)
    await session.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - disk-level failure
        logger.error(
            "file.delete.failed",
            extra={"receipt_id": receipt_id, "path": str(path), "error": str(exc)},
        )
        return
    logger.info("file.delete", extra={"receipt_id": receipt_id, "expense_id": expense_id})
