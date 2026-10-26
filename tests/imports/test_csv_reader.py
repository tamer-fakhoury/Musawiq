"""CSV reader and sales-template contracts."""

from __future__ import annotations

import pytest

from musawiq.imports.csv_reader import (
    CsvFormatError,
    CsvTooLargeError,
    read_csv,
)
from musawiq.imports.templates import SALES_TEMPLATE_CSV, template_bytes


def test_happy_path() -> None:
    parsed = read_csv(b"product_id,product_name\np1,Shirt\np2,Hat\n")

    assert parsed.headers == ["product_id", "product_name"]
    assert parsed.rows == [
        {"product_id": "p1", "product_name": "Shirt"},
        {"product_id": "p2", "product_name": "Hat"},
    ]
    assert parsed.row_numbers == [1, 2]
    assert parsed.delimiter == ","
    assert parsed.encoding == "utf-8"
    assert parsed.row_count == 2


def test_utf8_bom_is_removed() -> None:
    parsed = read_csv(b"\xef\xbb\xbfid,name\n1,Shirt\n")

    assert parsed.headers == ["id", "name"]
    assert parsed.rows == [{"id": "1", "name": "Shirt"}]
    assert parsed.encoding == "utf-8-sig"


def test_quoted_comma() -> None:
    parsed = read_csv(b'id,name\n1,"Shirt, Blue"\n')

    assert parsed.rows == [{"id": "1", "name": "Shirt, Blue"}]


def test_embedded_newline_in_quoted_field() -> None:
    parsed = read_csv(b'id,notes\n1,"line one\nline two"\n')

    assert parsed.row_count == 1
    assert parsed.rows == [{"id": "1", "notes": "line one\nline two"}]


def test_crlf_line_endings() -> None:
    parsed = read_csv(b"id,name\r\n1,Shirt\r\n2,Hat\r\n")

    assert parsed.headers == ["id", "name"]
    assert parsed.rows == [
        {"id": "1", "name": "Shirt"},
        {"id": "2", "name": "Hat"},
    ]


def test_duplicate_headers_are_rejected() -> None:
    with pytest.raises(CsvFormatError, match="unique"):
        read_csv(b"id,id\n1,2\n")


@pytest.mark.parametrize("data", [b"", b" \n", b"\n\n"])
def test_empty_input_is_rejected(data: bytes) -> None:
    with pytest.raises(CsvFormatError, match="empty|header"):
        read_csv(data)


def test_missing_header_row_is_rejected() -> None:
    with pytest.raises(CsvFormatError, match="header"):
        read_csv(b"\n1,2\n")


def test_non_utf8_bytes_are_rejected() -> None:
    with pytest.raises(CsvFormatError, match="UTF-8"):
        read_csv(b"id,name\n1,\xff\n")


def test_more_than_100k_rows_is_rejected() -> None:
    data = b"id,name\n" + b"1,x\n" * 100_001

    with pytest.raises(CsvTooLargeError):
        read_csv(data)


def test_sales_template_header_round_trips() -> None:
    parsed = read_csv(template_bytes())

    assert parsed.headers == [
        "product_id",
        "product_name",
        "order_date",
        "quantity",
        "sales_amount",
        "order_id",
        "currency",
        "sku",
    ]
    assert parsed.row_count == 1
    assert parsed.row_numbers == [1]
    assert parsed.rows[0]["product_id"] == "prod-001"
    assert parsed.rows[0]["product_name"] == "Classic T-Shirt"
    assert parsed.encoding == "utf-8"
    assert parsed.delimiter == ","
    assert not template_bytes().startswith(b"\xef\xbb\xbf")


def test_sales_template_is_utf8_text() -> None:
    assert SALES_TEMPLATE_CSV.startswith(
        "product_id,product_name,order_date,quantity,sales_amount,order_id,currency,sku\n"
    )
