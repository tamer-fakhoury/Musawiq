"""Import mapping service behaviour."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from musawiq.services.import_mapping import (
    MappingError,
    save_mapping,
    suggest_for_batch,
)

HEADERS = [
    "Product ID",
    "Product Name",
    "Order Date",
    "Quantity",
    "Sales Amount",
    "Order ID",
    "Currency",
    "SKU",
]
FULL_MAPPING = {
    "product_id": "Product ID",
    "product_name": "Product Name",
    "order_date": "Order Date",
    "quantity": "Quantity",
    "sales_amount": "Sales Amount",
    "order_id": "Order ID",
    "currency": "Currency",
    "sku": "SKU",
}


def test_suggestions_and_samples(session, tenant, mapping_env) -> None:
    result = suggest_for_batch(session, tenant, mapping_env.batch_id)

    assert result["headers"] == HEADERS
    assert result["suggested"] == FULL_MAPPING
    assert result["missing_required"] == []
    assert result["samples"]["Product Name"] == ["Widget", "Gadget", "Thing"]
    assert all(len(values) <= 3 for values in result["samples"].values())


def test_save_persists_mapping_and_links_batch(
    session, tenant, mapping_env
) -> None:
    mapping = {
        "product_id": "Product ID",
        "product_name": "Product Name",
        "order_date": "Order Date",
        "quantity": "Quantity",
        "sales_amount": "Sales Amount",
    }

    mapping_id = save_mapping(
        session,
        tenant,
        mapping_env.batch_id,
        mapping,
    )

    assert isinstance(mapping_id, uuid.UUID)
    stored = (
        session.execute(
            text(
                """
                SELECT store_id, name, source_type, mapping, is_default,
                       created_by
                FROM public.column_mappings
                WHERE id = :id
                """
            ),
            {"id": mapping_id},
        )
        .mappings()
        .one()
    )
    assert stored["store_id"] == mapping_env.store_id
    assert stored["name"] == f"import-{mapping_env.batch_id}"
    assert stored["source_type"] == "csv"
    assert stored["mapping"] == mapping
    assert stored["is_default"] is False
    assert stored["created_by"] == mapping_env.user_id

    batch = (
        session.execute(
            text(
                """
                SELECT column_mapping_id, status
                FROM public.import_batches
                WHERE id = :id
                """
            ),
            {"id": mapping_env.batch_id},
        )
        .mappings()
        .one()
    )
    assert batch["column_mapping_id"] == mapping_id
    assert batch["status"] == "uploaded"


def test_missing_required_raises(session, tenant, mapping_env) -> None:
    mapping = dict(FULL_MAPPING)
    mapping.pop("quantity")

    with pytest.raises(MappingError) as error:
        save_mapping(session, tenant, mapping_env.batch_id, mapping)

    assert error.value.code == "missing_required"


def test_duplicate_source_raises(session, tenant, mapping_env) -> None:
    mapping = dict(FULL_MAPPING)
    mapping["order_id"] = mapping["product_id"]

    with pytest.raises(MappingError) as error:
        save_mapping(session, tenant, mapping_env.batch_id, mapping)

    assert error.value.code == "duplicate_source"


def test_unknown_source_raises(session, tenant, mapping_env) -> None:
    mapping = dict(FULL_MAPPING)
    mapping["sku"] = "Missing Header"

    with pytest.raises(MappingError) as error:
        save_mapping(session, tenant, mapping_env.batch_id, mapping)

    assert error.value.code == "unknown_source"
