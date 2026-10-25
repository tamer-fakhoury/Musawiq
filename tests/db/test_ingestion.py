"""Integrations and ingestion tables: constraints (DB-0.5)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

DEDUPE_HASH = "a" * 64


def _insert_user(conn, email="owner@example.com"):
    return conn.execute(
        text(
            """
            INSERT INTO users (email, full_name, role, status)
            VALUES (:email, 'Test User', 'owner', 'active')
            RETURNING id
            """
        ),
        {"email": email},
    ).scalar_one()


def _insert_store(conn, owner_user_id, slug="demo-store"):
    return conn.execute(
        text(
            """
            INSERT INTO stores (
                owner_user_id, name, slug, status,
                default_currency, default_language, timezone, country_code,
                onboarding_status
            )
            VALUES (
                :owner_user_id, 'Demo Store', :slug, 'active',
                'USD', 'en', 'UTC', 'US', 'completed'
            )
            RETURNING id
            """
        ),
        {"owner_user_id": owner_user_id, "slug": slug},
    ).scalar_one()


def _seed_store(conn, email="owner@example.com", slug="demo-store"):
    user_id = _insert_user(conn, email=email)
    store_id = _insert_store(conn, user_id, slug=slug)
    return user_id, store_id


def _insert_stored_file(conn, store_id, purpose="sales_csv"):
    return conn.execute(
        text(
            """
            INSERT INTO stored_files (
                store_id, purpose, original_filename, mime_type, size_bytes,
                checksum_sha256, storage_provider, storage_key, status
            )
            VALUES (
                :store_id, :purpose, 'data.csv', 'text/csv', 0,
                repeat('a', 64), 'local', 'key', 'staged'
            )
            RETURNING id
            """
        ),
        {"store_id": store_id, "purpose": purpose},
    ).scalar_one()


def _insert_store_connection(conn, store_id):
    return conn.execute(
        text(
            """
            INSERT INTO store_connections (
                store_id, provider, external_store_id, status
            )
            VALUES (:store_id, 'shopify', 'external-store', 'connected')
            RETURNING id
            """
        ),
        {"store_id": store_id},
    ).scalar_one()


def _insert_import_batch(
    conn,
    store_id,
    created_by,
    source_type="csv",
    stored_file_id=None,
    store_connection_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO import_batches (
                store_id, source_type, stored_file_id, store_connection_id,
                status, created_by
            )
            VALUES (
                :store_id, :source_type, :stored_file_id, :store_connection_id,
                'uploaded', :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "source_type": source_type,
            "stored_file_id": stored_file_id,
            "store_connection_id": store_connection_id,
            "created_by": created_by,
        },
    ).scalar_one()


def _insert_product(conn, store_id, external_product_id=None, sku=None):
    return conn.execute(
        text(
            """
            INSERT INTO products (
                store_id, name, currency, source, external_product_id, sku
            )
            VALUES (:store_id, 'Product', 'USD', 'manual', :external_product_id, :sku)
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "external_product_id": external_product_id,
            "sku": sku,
        },
    ).scalar_one()


def _insert_order(conn, store_id, dedupe_hash=None):
    return conn.execute(
        text(
            """
            INSERT INTO orders (
                store_id, origin, status, currency, placed_at, dedupe_hash
            )
            VALUES (:store_id, 'imported', 'pending', 'USD', now(), :dedupe_hash)
            RETURNING id
            """
        ),
        {"store_id": store_id, "dedupe_hash": dedupe_hash},
    ).scalar_one()


def _insert_import_row(conn, store_id, import_batch_id, row_number=1):
    return conn.execute(
        text(
            """
            INSERT INTO import_rows (
                store_id, import_batch_id, row_number, raw_data, status
            )
            VALUES (:store_id, :import_batch_id, :row_number, '{}'::jsonb, 'valid')
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "import_batch_id": import_batch_id,
            "row_number": row_number,
        },
    ).scalar_one()


def test_import_batches_csv_requires_stored_file(conn):
    created_by, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_import_batch(
            conn, store_id, created_by, source_type="csv", stored_file_id=None
        )


def test_import_batches_store_connection_requires_connection(conn):
    created_by, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_import_batch(
            conn,
            store_id,
            created_by,
            source_type="store_connection",
            store_connection_id=None,
        )


def test_import_batches_store_connection_source_is_valid(conn):
    created_by, store_id = _seed_store(conn)
    connection_id = _insert_store_connection(conn, store_id)

    batch_id = _insert_import_batch(
        conn,
        store_id,
        created_by,
        source_type="store_connection",
        store_connection_id=connection_id,
    )
    assert batch_id is not None


def test_order_items_quantity_must_be_positive(conn):
    _, store_id = _seed_store(conn)
    order_id = _insert_order(conn, store_id)

    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO order_items (
                    store_id, order_id, product_name_snapshot, quantity,
                    unit_price_minor, line_total_minor, currency
                )
                VALUES (:store_id, :order_id, 'Thing', 0, 100, 100, 'USD')
                """
            ),
            {"store_id": store_id, "order_id": order_id},
        )


def test_orders_dedupe_hash_is_unique(conn):
    _, store_id = _seed_store(conn)
    _insert_order(conn, store_id, dedupe_hash=DEDUPE_HASH)

    with pytest.raises(DBAPIError):
        _insert_order(conn, store_id, dedupe_hash=DEDUPE_HASH)


def test_products_external_product_id_is_unique(conn):
    _, store_id = _seed_store(conn)
    _insert_product(conn, store_id, external_product_id="ext-1")

    with pytest.raises(DBAPIError):
        _insert_product(conn, store_id, external_product_id="ext-1")


def test_products_sku_is_unique(conn):
    _, store_id = _seed_store(conn)
    _insert_product(conn, store_id, sku="SKU-1")

    with pytest.raises(DBAPIError):
        _insert_product(conn, store_id, sku="SKU-1")


def test_products_allow_multiple_null_external_ids(conn):
    _, store_id = _seed_store(conn)
    _insert_product(conn, store_id)
    _insert_product(conn, store_id)

    count = conn.execute(
        text("SELECT count(*) FROM products WHERE external_product_id IS NULL")
    ).scalar_one()
    assert count == 2


def test_content_providers_global_code_is_unique(conn):
    conn.execute(
        text(
            """
            INSERT INTO content_providers (store_id, code, name)
            VALUES (NULL, 'openai', 'OpenAI')
            """
        )
    )

    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO content_providers (store_id, code, name)
                VALUES (NULL, 'openai', 'OpenAI Copy')
                """
            )
        )


def test_content_providers_store_code_may_repeat_global_code(conn):
    _, store_id = _seed_store(conn)
    conn.execute(
        text(
            """
            INSERT INTO content_providers (store_id, code, name)
            VALUES (NULL, 'openai', 'OpenAI')
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO content_providers (store_id, code, name)
            VALUES (:store_id, 'openai', 'Store OpenAI')
            """
        ),
        {"store_id": store_id},
    )

    count = conn.execute(text("SELECT count(*) FROM content_providers")).scalar_one()
    assert count == 2


def test_import_rows_row_number_is_unique(conn):
    created_by, store_id = _seed_store(conn)
    stored_file_id = _insert_stored_file(conn, store_id)
    batch_id = _insert_import_batch(
        conn, store_id, created_by, stored_file_id=stored_file_id
    )
    _insert_import_row(conn, store_id, batch_id, row_number=1)

    with pytest.raises(DBAPIError):
        _insert_import_row(conn, store_id, batch_id, row_number=1)


def test_stored_files_purpose_check(conn):
    _, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_stored_file(conn, store_id, purpose="not_a_purpose")
