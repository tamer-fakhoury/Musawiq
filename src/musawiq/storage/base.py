"""Storage adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    checksum_sha256: str
    content_type: str
    original_filename: str


class Storage(Protocol):
    def save(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        purpose: str,
    ) -> StoredObject:
        ...

    def open(self, key: str) -> bytes:
        ...

    def delete(self, key: str) -> None:
        ...


__all__ = ["Storage", "StoredObject"]
