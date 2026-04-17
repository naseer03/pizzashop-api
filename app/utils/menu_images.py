"""Save and remove uploaded menu item images on disk."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.utils.responses import err

_ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_FILENAME_RE = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp|gif)$")


def menu_items_upload_dir() -> Path:
    return Path(settings.media_root).resolve() / "menu_items"


def public_url_for_filename(filename: str) -> str:
    return f"{settings.media_url_prefix.rstrip('/')}/{filename}"


async def save_menu_item_image(upload: UploadFile) -> str:
    raw_ct = upload.content_type or ""
    content_type = raw_ct.split(";", 1)[0].strip().lower()
    ext = _ALLOWED_TYPES.get(content_type)
    if not ext:
        allowed = ", ".join(sorted(_ALLOWED_TYPES))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=err("UNSUPPORTED_MEDIA_TYPE", f"Allowed image types: {allowed}."),
        )
    data = await upload.read()
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=err("FILE_TOO_LARGE", f"Maximum upload size is {settings.max_upload_mb} MB."),
        )
    name = f"{uuid.uuid4().hex}{ext}"
    dest_dir = menu_items_upload_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    dest.write_bytes(data)
    return public_url_for_filename(name)


def try_remove_stored_menu_image(url: str | None) -> None:
    """Delete a file previously saved by this API (ignores external URLs)."""
    if not url:
        return
    prefix = settings.media_url_prefix.rstrip("/") + "/"
    if not url.startswith(prefix):
        return
    fname = Path(url.removeprefix(prefix)).name
    if not fname or not _FILENAME_RE.match(fname):
        return
    path = menu_items_upload_dir() / fname
    if path.is_file():
        path.unlink()
