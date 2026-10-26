"""Local filesystem storage adapter with upload validation."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from musawiq.storage.base import StoredObject

DEFAULT_MAX_SIZE_BYTES = 20 * 1024 * 1024

IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
FEEDBACK_CONTENT_TYPES = frozenset(
    {
        "text/csv",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)

ALLOWED_CONTENT_TYPES: dict[str, frozenset[str]] = {
    "sales_csv": frozenset({"text/csv"}),
    "feedback_file": FEEDBACK_CONTENT_TYPES,
    "product_image": IMAGE_CONTENT_TYPES,
    "ad_creative": IMAGE_CONTENT_TYPES,
    "ai_image": IMAGE_CONTENT_TYPES,
    "creative": IMAGE_CONTENT_TYPES,
    "ai_video": frozenset({"video/mp4", "video/webm"}),
    "deposit_evidence": frozenset(
        {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    ),
}

DEFAULT_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "text/csv",
        "text/plain",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

_PURPOSE = re.compile(r"^[a-z][a-z0-9_]*$")
_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_filename(filename: str) -> str:
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("filename must be a non-empty string")
    basename = filename.replace("\\", "/").strip().rsplit("/", 1)[-1]
    if basename in {"", ".", ".."}:
        raise ValueError("filename must not be empty or a directory traversal")
    if "\x00" in basename:
        raise ValueError("filename contains a null byte")
    return basename


def _normalized_content_type(content_type: str) -> str:
    if not isinstance(content_type, str) or not content_type.strip():
        raise ValueError("content_type must be a non-empty string")
    return content_type.split(";", 1)[0].strip().lower()


class LocalStorage:
    """Store objects under ``root/<purpose>/<uuid>``."""

    def __init__(
        self,
        root: Path,
        *,
        max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    ) -> None:
        if not isinstance(root, Path):
            root = Path(root)
        if max_size_bytes < 1:
            raise ValueError("max_size_bytes must be positive")
        self.root = root
        self.max_size_bytes = max_size_bytes

    def _validate_purpose(self, purpose: str) -> str:
        if not isinstance(purpose, str) or not _PURPOSE.fullmatch(purpose):
            raise ValueError("purpose must be a lowercase identifier")
        return purpose

    def _allowed(self, purpose: str) -> frozenset[str]:
        return ALLOWED_CONTENT_TYPES.get(purpose, DEFAULT_CONTENT_TYPES)

    def _find(self, key: str) -> Path | None:
        if not isinstance(key, str) or not _KEY.fullmatch(key) or key in {
            ".",
            "..",
        }:
            raise ValueError("key must be a safe generated identifier")
        if not self.root.is_dir():
            return None
        for purpose_dir in sorted(self.root.iterdir()):
            if not purpose_dir.is_dir():
                continue
            candidate = purpose_dir / key
            if candidate.is_file():
                return candidate
        return None

    def save(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        purpose: str,
    ) -> StoredObject:
        if not isinstance(data, (bytes, bytearray)):
            raise ValueError("data must be bytes")
        payload = bytes(data)
        if len(payload) > self.max_size_bytes:
            raise ValueError(
                f"file exceeds the {self.max_size_bytes}-byte size limit"
            )

        safe_name = _safe_filename(filename)
        normalized_type = _normalized_content_type(content_type)
        safe_purpose = self._validate_purpose(purpose)
        if normalized_type not in self._allowed(safe_purpose):
            raise ValueError(
                f"content type {normalized_type!r} is not allowed for "
                f"purpose {safe_purpose!r}"
            )

        purpose_dir = self.root / safe_purpose
        purpose_dir.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256(payload).hexdigest()

        for _ in range(10):
            key = str(uuid.uuid4())
            path = purpose_dir / key
            try:
                with path.open("xb") as handle:
                    handle.write(payload)
            except FileExistsError:
                continue
            return StoredObject(
                key=key,
                size_bytes=len(payload),
                checksum_sha256=checksum,
                content_type=normalized_type,
                original_filename=safe_name,
            )
        raise RuntimeError("could not allocate a unique storage key")

    def open(self, key: str) -> bytes:
        path = self._find(key)
        if path is None:
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._find(key)
        if path is not None:
            path.unlink(missing_ok=True)


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "DEFAULT_CONTENT_TYPES",
    "DEFAULT_MAX_SIZE_BYTES",
    "LocalStorage",
]
