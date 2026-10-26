"""Suggest source-column to canonical-target mappings."""

from __future__ import annotations

import re

REQUIRED_TARGETS = {
    "product_id",
    "product_name",
    "order_date",
    "quantity",
    "sales_amount",
}
OPTIONAL_TARGETS = {"order_id", "currency", "sku"}

ALIASES: dict[str, tuple[str, ...]] = {
    "product_id": ("product_id", "productid", "item_id", "sku_id"),
    "product_name": ("product_name", "name", "title", "item"),
    "order_date": ("order_date", "date", "created_at", "order_created_at"),
    "quantity": ("quantity", "qty", "units"),
    "sales_amount": ("sales_amount", "amount", "total", "revenue", "price"),
    "order_id": ("order_id", "order_number", "orderid"),
    "currency": ("currency", "currency_code"),
    "sku": ("sku", "variant_sku"),
}

_TARGET_ORDER = (
    "product_id",
    "product_name",
    "order_date",
    "quantity",
    "sales_amount",
    "order_id",
    "currency",
    "sku",
)


def normalize_header(value: str) -> str:
    """Lowercase and collapse whitespace/underscore runs to one underscore."""
    text = value.strip().lower()
    return re.sub(r"[\s_]+", "_", text).strip("_")


_NORMALIZED_ALIASES = {
    target: tuple(normalize_header(alias) for alias in aliases)
    for target, aliases in ALIASES.items()
}


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Return ``target -> original header`` with at most one use per header."""
    normalized = [
        (index, header, normalize_header(header))
        for index, header in enumerate(headers)
    ]
    used: set[int] = set()
    mapping: dict[str, str] = {}

    for index, header, candidate in normalized:
        if index in used:
            continue
        for target in _TARGET_ORDER:
            if target in mapping:
                continue
            if candidate in _NORMALIZED_ALIASES[target]:
                mapping[target] = header
                used.add(index)
                break
    return mapping


def missing_required(mapping: dict[str, str]) -> set[str]:
    return REQUIRED_TARGETS - set(mapping)


__all__ = [
    "ALIASES",
    "OPTIONAL_TARGETS",
    "REQUIRED_TARGETS",
    "missing_required",
    "normalize_header",
    "suggest_mapping",
]
