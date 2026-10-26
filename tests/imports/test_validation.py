"""Row validation and dedupe hashing."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from musawiq.imports.validation import Issue, dedupe_hash, validate_row

MAPPING = {
    "product_id": "product_id",
    "product_name": "product_name",
    "order_date": "order_date",
    "quantity": "quantity",
    "sales_amount": "sales_amount",
    "order_id": "order_id",
    "currency": "currency",
    "sku": "sku",
}


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "product_id": "P-1",
        "product_name": "Widget",
        "order_date": "2024-01-15",
        "quantity": "2",
        "sales_amount": "10.50",
        "order_id": "O-1",
        "currency": "SAR",
        "sku": "SKU-1",
    }
    row.update(overrides)
    return row


def test_valid_row_is_mapped_and_typed() -> None:
    normalized, issues = validate_row(
        _row(),
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="USD",
    )

    assert issues == []
    assert normalized["product_id"] == "P-1"
    assert normalized["product_name"] == "Widget"
    assert normalized["quantity"] == 2
    assert normalized["sales_amount"] == Decimal("10.50")
    assert normalized["currency"] == "SAR"
    assert normalized["order_id"] == "O-1"
    assert normalized["sku"] == "SKU-1"
    assert isinstance(normalized["order_date"], datetime)
    assert normalized["order_date"].tzinfo == ZoneInfo("Asia/Riyadh")
    assert normalized["order_date"].hour == 0


def test_bad_date_returns_an_issue() -> None:
    _, issues = validate_row(
        _row(order_date="not-a-date"),
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="SAR",
    )

    assert any(
        issue.field == "order_date" and issue.code == "invalid_date"
        for issue in issues
    )


def test_zero_or_negative_quantity_returns_an_issue() -> None:
    for value in ("0", "-2", "1.5", "abc"):
        _, issues = validate_row(
            _row(quantity=value),
            MAPPING,
            timezone="Asia/Riyadh",
            default_currency="SAR",
        )
        assert any(issue.field == "quantity" for issue in issues)


def test_negative_amount_returns_an_issue() -> None:
    _, issues = validate_row(
        _row(sales_amount="-0.01"),
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="SAR",
    )

    assert any(
        issue.field == "sales_amount" and issue.code == "invalid_amount"
        for issue in issues
    )


def test_bad_currency_returns_an_issue() -> None:
    _, issues = validate_row(
        _row(currency="US"),
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="SAR",
    )

    assert any(
        issue.field == "currency" and issue.code == "invalid_currency"
        for issue in issues
    )


def test_default_currency_is_used_when_currency_is_blank() -> None:
    normalized, issues = validate_row(
        _row(currency=""),
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="usd",
    )

    assert issues == []
    assert normalized["currency"] == "USD"


def test_missing_required_values_return_issues() -> None:
    _, issues = validate_row(
        _row(product_id="", product_name="", order_date=""),
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="SAR",
    )

    fields = {issue.field for issue in issues}
    assert {"product_id", "product_name", "order_date"} <= fields


def test_unknown_and_unmapped_columns_are_ignored() -> None:
    row = _row(customer_phone="+966500000000")
    row["not_mapped"] = "ignored"

    normalized, issues = validate_row(
        row,
        MAPPING,
        timezone="Asia/Riyadh",
        default_currency="SAR",
    )

    assert issues == []
    assert "customer_phone" not in normalized
    assert "not_mapped" not in normalized


def test_bad_timezone_raises_value_error() -> None:
    with pytest.raises(ValueError, match="timezone"):
        validate_row(
            _row(),
            MAPPING,
            timezone="Not/AZone",
            default_currency="SAR",
        )


def test_dedupe_hash_order_id_rule_ignores_other_fields() -> None:
    first = {
        "order_id": "O-1",
        "product_id": "P-1",
        "order_date": "2024-01-15",
        "quantity": 1,
        "sales_amount": Decimal("10.00"),
    }
    second = {
        "order_id": "O-1",
        "product_id": "P-1",
        "order_date": "2024-02-20",
        "quantity": 9,
        "sales_amount": Decimal("99.00"),
    }

    assert dedupe_hash(first) == dedupe_hash(second)


def test_dedupe_hash_without_order_id_uses_product_date_quantity_amount() -> None:
    first = {
        "product_id": "P-1",
        "order_date": datetime(2024, 1, 15, tzinfo=ZoneInfo("UTC")),
        "quantity": 2,
        "sales_amount": Decimal("10.50"),
    }
    second = {
        "product_id": "p-1",
        "order_date": "2024-01-15T00:00:00+00:00",
        "quantity": "2",
        "sales_amount": "10.5",
    }

    assert dedupe_hash(first) == dedupe_hash(second)


def test_dedupe_hash_differs_across_products() -> None:
    first = {
        "product_id": "P-1",
        "order_date": "2024-01-15",
        "quantity": 2,
        "sales_amount": Decimal("10.50"),
    }
    second = {
        "product_id": "P-2",
        "order_date": "2024-01-15",
        "quantity": 2,
        "sales_amount": Decimal("10.50"),
    }

    assert dedupe_hash(first) != dedupe_hash(second)


def test_issue_is_a_small_dataclass() -> None:
    issue = Issue("quantity", "invalid_quantity", "bad", "0")

    assert issue.field == "quantity"
    assert issue.raw_value == "0"
