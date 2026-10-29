"""FR-1.2.3 customer feedback intake."""

from __future__ import annotations

import io
import uuid
import zipfile
from xml.sax.saxutils import escape

from sqlalchemy import text

from musawiq.services import feedback as feedback_service

CSV_CONTENT_TYPE = "text/csv"
TXT_CONTENT_TYPE = "text/plain"
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _profile(client, tenant, taxonomy) -> str:
    response = client.post(
        "/audience-profiles",
        json={
            "niche_ids": [str(taxonomy[1])],
            "languages": ["en"],
        },
        headers=_headers(tenant),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _manual(client, tenant, **overrides):
    payload = {"text": "Customers keep asking for a larger size."}
    payload.update(overrides)
    return client.post(
        "/feedback", json=payload, headers=_headers(tenant)
    )


def _upload(client, tenant, filename, content, content_type):
    return client.post(
        "/feedback/file",
        files={"file": (filename, content, content_type)},
        headers=_headers(tenant),
    )


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            column = chr(ord("A") + column_index)
            cells.append(
                f'<c r="{column}{row_index}" t="inlineStr">'
                f"<is><t>{escape(value)}</t></is></c>"
            )
        row_xml.append(
            f'<row r="{row_index}">{"".join(cells)}</row>'
        )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>'
        + "".join(row_xml)
        + "</sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def test_manual_feedback_is_timestamped_and_linked_to_store_and_profile(
    client, tenant, taxonomy, db_engine
) -> None:
    profile_id = _profile(client, tenant, taxonomy)

    response = _manual(
        client,
        tenant,
        language="en",
        sentiment="positive",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["store_id"] == str(tenant.store_id)
    assert body["audience_profile_id"] == profile_id
    assert body["source"] == "manual"
    assert body["stored_file_id"] is None
    assert body["sentiment"] == "positive"
    assert body["captured_at"] is not None

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT store_id, audience_profile_id, source, "text",
                       language, sentiment, captured_at
                FROM feedback_items WHERE id = :id
                """
            ),
            {"id": uuid.UUID(body["id"])},
        ).mappings().one()
    assert row["store_id"] == tenant.store_id
    assert row["audience_profile_id"] == uuid.UUID(profile_id)
    assert row["source"] == "manual"
    assert row["text"] == "Customers keep asking for a larger size."
    assert row["language"] == "en"
    assert row["sentiment"] == "positive"
    assert row["captured_at"] is not None

    listed = client.get("/feedback", headers=_headers(tenant))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_manual_rejection_is_field_specific_without_echoing_text(
    client, tenant
) -> None:
    empty = _manual(client, tenant, text="  ")
    assert empty.status_code == 422
    assert empty.json()["error"]["fields"] == {"text": "text is required"}

    secret = "customer phone 0500000000"
    invalid = _manual(
        client,
        tenant,
        text=secret,
        sentiment="angry",
    )
    assert invalid.status_code == 422
    assert secret not in invalid.text


def test_csv_txt_and_xlsx_files_are_accepted_and_referenced(
    client, tenant, taxonomy, db_engine
) -> None:
    _profile(client, tenant, taxonomy)

    csv_response = _upload(
        client,
        tenant,
        "feedback.csv",
        b"text,language,sentiment\n"
        b"Great product,en,positive\n"
        b"Needs a bigger size,ar,neutral\n",
        CSV_CONTENT_TYPE,
    )
    assert csv_response.status_code == 201, csv_response.text
    csv_body = csv_response.json()
    assert csv_body["count"] == 2
    assert csv_body["format"] == "csv"
    assert csv_body["file"]["purpose"] == "feedback_file"

    txt_response = _upload(
        client,
        tenant,
        "feedback.txt",
        "First comment\nSecond comment\n".encode("utf-8"),
        TXT_CONTENT_TYPE,
    )
    assert txt_response.status_code == 201, txt_response.text
    assert txt_response.json()["count"] == 2

    xlsx_response = _upload(
        client,
        tenant,
        "feedback.xlsx",
        _xlsx_bytes(
            [
                ["text", "language", "sentiment"],
                ["Loved the packaging", "en", "positive"],
            ]
        ),
        XLSX_CONTENT_TYPE,
    )
    assert xlsx_response.status_code == 201, xlsx_response.text
    xlsx_body = xlsx_response.json()
    assert xlsx_body["count"] == 1
    assert xlsx_body["items"][0]["text"] == "Loved the packaging"

    with db_engine.connect() as conn:
        stored = conn.execute(
            text(
                """
                SELECT purpose, status, mime_type, size_bytes
                FROM stored_files WHERE id = :id
                """
            ),
            {"id": uuid.UUID(csv_body["file"]["id"])},
        ).mappings().one()
        items = conn.execute(
            text(
                """
                SELECT source, stored_file_id, "text"
                FROM feedback_items
                WHERE store_id = :store_id
                ORDER BY captured_at, id
                """
            ),
            {"store_id": tenant.store_id},
        ).mappings().all()
    assert stored["purpose"] == "feedback_file"
    assert stored["status"] == "committed"
    assert stored["mime_type"] == CSV_CONTENT_TYPE
    assert stored["size_bytes"] > 0
    assert all(item["source"] == "file" for item in items)
    assert all(item["stored_file_id"] is not None for item in items)


def test_file_type_size_and_encoding_rejections_are_specific(
    client, tenant, monkeypatch
) -> None:
    wrong_type = _upload(
        client,
        tenant,
        "feedback.pdf",
        b"%PDF",
        "application/pdf",
    )
    assert wrong_type.status_code == 422
    assert "unsupported file type" in wrong_type.json()["error"]["fields"]["file"]

    content = b"text\nA valid comment\n"
    monkeypatch.setattr(
        feedback_service, "MAX_FEEDBACK_BYTES", len(content) - 1
    )
    too_large = _upload(
        client, tenant, "feedback.csv", content, CSV_CONTENT_TYPE
    )
    assert too_large.status_code == 422
    assert too_large.json()["error"]["fields"]["file"]

    bad_encoding = _upload(
        client,
        tenant,
        "feedback.txt",
        b"\xff\xfe\xfa",
        TXT_CONTENT_TYPE,
    )
    assert bad_encoding.status_code == 422
    assert (
        bad_encoding.json()["error"]["fields"]["file"]
        == "file must be UTF-8 encoded"
    )


def test_invalid_file_row_does_not_echo_feedback_text(
    client, tenant
) -> None:
    secret = "call me on 0500000000"
    response = _upload(
        client,
        tenant,
        "feedback.csv",
        f"text,sentiment\n{secret},angry\n".encode("utf-8"),
        CSV_CONTENT_TYPE,
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert "row 2" in response.json()["error"]["fields"]["file"]


def test_feedback_is_store_scoped(
    client, tenant, make_tenant
) -> None:
    _manual(client, tenant)
    other = make_tenant()

    response = client.get("/feedback", headers=_headers(other))
    assert response.status_code == 200
    assert response.json() == []
