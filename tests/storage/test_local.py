"""Local storage adapter behaviour."""

from __future__ import annotations

import hashlib

import pytest

from musawiq.storage import LocalStorage, StoredObject, get_storage


def test_save_open_delete_round_trip(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    payload = b"id,name,amount\n1,Widget,100\n"

    saved = storage.save(
        payload,
        filename="sales.csv",
        content_type="text/csv",
        purpose="sales_csv",
    )

    assert isinstance(saved, StoredObject)
    assert saved.size_bytes == len(payload)
    assert storage.open(saved.key) == payload
    assert (tmp_path / "sales_csv" / saved.key).is_file()

    storage.delete(saved.key)
    assert not (tmp_path / "sales_csv" / saved.key).exists()


def test_checksum_matches_sha256(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    payload = b"feedback text"

    saved = storage.save(
        payload,
        filename="feedback.txt",
        content_type="text/plain",
        purpose="feedback_file",
    )

    assert saved.checksum_sha256 == hashlib.sha256(payload).hexdigest()


def test_oversized_payload_is_rejected(tmp_path) -> None:
    storage = LocalStorage(tmp_path, max_size_bytes=4)

    with pytest.raises(ValueError, match="size limit"):
        storage.save(
            b"12345",
            filename="image.png",
            content_type="image/png",
            purpose="product_image",
        )


def test_disallowed_content_type_is_rejected(tmp_path) -> None:
    storage = LocalStorage(tmp_path)

    with pytest.raises(ValueError, match="not allowed"):
        storage.save(
            b"<html></html>",
            filename="page.html",
            content_type="text/html",
            purpose="product_image",
        )


def test_path_traversal_filename_is_neutralised(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    payload = b"contents"

    saved = storage.save(
        payload,
        filename="../../etc/passwd",
        content_type="text/plain",
        purpose="feedback_file",
    )

    assert saved.original_filename == "passwd"
    assert saved.key not in {"../../etc/passwd", "etc/passwd"}
    assert (tmp_path / "feedback_file" / saved.key).is_file()
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path.parent / "etc").exists()
    assert storage.open(saved.key) == payload


def test_empty_and_parent_filenames_are_rejected(tmp_path) -> None:
    storage = LocalStorage(tmp_path)

    for filename in ("", "   ", "..", "folder/..", "folder/"):
        with pytest.raises(ValueError):
            storage.save(
                b"x",
                filename=filename,
                content_type="text/plain",
                purpose="feedback_file",
            )


def test_two_saves_never_collide(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    payload = b"same bytes"

    first = storage.save(
        payload,
        filename="first.csv",
        content_type="text/csv",
        purpose="sales_csv",
    )
    second = storage.save(
        payload,
        filename="second.csv",
        content_type="text/csv",
        purpose="sales_csv",
    )

    assert first.key != second.key
    assert (tmp_path / "sales_csv" / first.key).is_file()
    assert (tmp_path / "sales_csv" / second.key).is_file()


def test_delete_is_idempotent(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    saved = storage.save(
        b"x",
        filename="x.png",
        content_type="image/png",
        purpose="product_image",
    )

    storage.delete(saved.key)
    storage.delete(saved.key)

    with pytest.raises(FileNotFoundError):
        storage.open(saved.key)


def test_storage_is_found_by_key_across_purpose_directories(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    csv_object = storage.save(
        b"a,b\n1,2\n",
        filename="a.csv",
        content_type="text/csv",
        purpose="sales_csv",
    )
    image_object = storage.save(
        b"\x89PNG\r\n",
        filename="a.png",
        content_type="image/png",
        purpose="product_image",
    )

    assert storage.open(csv_object.key) == b"a,b\n1,2\n"
    assert storage.open(image_object.key) == b"\x89PNG\r\n"


def test_get_storage_uses_environment_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MUSAWIQ_STORAGE_ROOT", str(tmp_path / "uploads"))

    storage = get_storage()

    assert isinstance(storage, LocalStorage)
    assert storage.root == tmp_path / "uploads"
