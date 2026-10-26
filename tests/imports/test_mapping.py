"""Column mapping suggestions."""

from __future__ import annotations

from musawiq.imports.mapping import (
    OPTIONAL_TARGETS,
    REQUIRED_TARGETS,
    missing_required,
    normalize_header,
    suggest_mapping,
)


def test_aliases_and_normalization_are_suggested() -> None:
    headers = [
        "Product ID",
        "Name",
        "Date",
        "Qty",
        "Amount",
        "Order Number",
        "Currency Code",
        "Variant SKU",
    ]

    mapping = suggest_mapping(headers)

    assert mapping == {
        "product_id": "Product ID",
        "product_name": "Name",
        "order_date": "Date",
        "quantity": "Qty",
        "sales_amount": "Amount",
        "order_id": "Order Number",
        "currency": "Currency Code",
        "sku": "Variant SKU",
    }


def test_header_normalization_collapses_spaces_and_underscores() -> None:
    assert normalize_header("  Product__ID  ") == "product_id"
    assert normalize_header("Order   Date") == "order_date"
    assert normalize_header("ProductID") == "productid"


def test_first_matching_header_wins_for_a_target() -> None:
    mapping = suggest_mapping(["productid", "product_id", "name"])

    assert mapping["product_id"] == "productid"
    assert "product_id" not in set(mapping.values()) - {"productid"}


def test_each_source_header_is_used_at_most_once() -> None:
    mapping = suggest_mapping(["product_id", "ProductID", "name"])

    assert mapping["product_id"] == "product_id"
    assert len(set(mapping.values())) == len(mapping)


def test_missing_required_reports_required_targets() -> None:
    mapping = suggest_mapping(["name", "qty"])
    missing = missing_required(mapping)

    assert missing == {"product_id", "order_date", "sales_amount"}
    assert REQUIRED_TARGETS == {
        "product_id",
        "product_name",
        "order_date",
        "quantity",
        "sales_amount",
    }
    assert OPTIONAL_TARGETS == {"order_id", "currency", "sku"}


def test_unknown_headers_are_ignored() -> None:
    mapping = suggest_mapping(["customer_phone", "name"])

    assert mapping == {"product_name": "name"}
