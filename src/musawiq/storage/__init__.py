"""Storage adapters."""

from __future__ import annotations

import os
from pathlib import Path

from musawiq.storage.base import Storage, StoredObject
from musawiq.storage.local import LocalStorage


def get_storage() -> Storage:
    root = Path(os.getenv("MUSAWIQ_STORAGE_ROOT", "./var/storage"))
    return LocalStorage(root)


__all__ = ["LocalStorage", "Storage", "StoredObject", "get_storage"]
