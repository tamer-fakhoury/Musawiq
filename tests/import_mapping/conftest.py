"""Database and storage fixtures for import-mapping service tests."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext, set_local_tenant
from musawiq.storage import LocalStorage
from scripts.gen_schema_docs import libpq_url
from scripts.seed_dev import scratch_database

CSV_DATA = b"""Product ID,Product Name,Order Date,Quantity,Sales Amount,Order ID,Currency,SKU
P-1,Widget,2024-01-01,2,10.50,O-1,SAR,SKU-1
P-2,Gadget,2024-01-02,1,20.00,O-2,SAR,SKU-2
P-3,Thing,2024-01-03,3,30.00,O-3,SAR,SKU-3
P-4,Fourth,2024-01-04,4,40.00,O-4,SAR,SKU-4
"""


@dataclass(frozen=True)
class MappingEnv:
    url: str
    store_id: uuid.UUID
    user_id: uuid.UUID
    batch_id: uuid.UUID
    storage_root: Path


@pytest.fixture(scope="module")
def mapping_env(tmp_path_factory) -> MappingEnv:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail("MUSAWIQ_ADMIN_DATABASE_URL is not set")

    root = tmp_path_factory.mktemp("import-storage")
    user_id, store_id, batch_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    saved = LocalStorage(root).save(
        CSV_DATA,
        filename="sales.csv",
        content_type="text/csv",
        purpose="sales_csv",
    )

    with scratch_database(admin_url) as url:
        with psycopg.connect(libpq_url(url), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.users (id, email, full_name, role, status)
                    VALUES (%s, %s, 'Mapping Owner', 'owner', 'active')
                    """,
                    (user_id, f"mapping-{user_id.hex}@dev.local"),
                )
                cur.execute(
                    """
                    INSERT INTO public.stores (
                        id, owner_user_id, name, slug, status,
                        default_currency, default_language, timezone,
                        country_code, onboarding_status
                    ) VALUES (
                        %s, %s, 'Mapping Store', %s, 'active',
                        'SAR', 'ar', 'Asia/Riyadh', 'SA', 'completed'
                    )
                    """,
                    (store_id, user_id, f"mapping-{store_id.hex}"),
                )
                cur.execute(
                    """
                    INSERT INTO public.stored_files (
                        id, store_id, purpose, original_filename, mime_type,
                        size_bytes, checksum_sha256, storage_provider,
                        storage_key, status, uploaded_by_user_id
                    ) VALUES (
                        %s, %s, 'sales_csv', 'sales.csv', 'text/csv',
                        %s, %s, 'local', %s, 'committed', %s
                    )
                    """,
                    (
                        uuid.uuid4(),
                        store_id,
                        saved.size_bytes,
                        saved.checksum_sha256,
                        saved.key,
                        user_id,
                    ),
                )
                stored_file_id = cur.execute(
                    "SELECT id FROM public.stored_files WHERE store_id = %s",
                    (store_id,),
                ).fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO public.import_batches (
                        id, store_id, source_type, stored_file_id, status,
                        created_by
                    ) VALUES (%s, %s, 'csv', %s, 'uploaded', %s)
                    """,
                    (batch_id, store_id, stored_file_id, user_id),
                )
        yield MappingEnv(url, store_id, user_id, batch_id, root)


@pytest.fixture()
def session(mapping_env: MappingEnv, monkeypatch):
    monkeypatch.setenv("MUSAWIQ_STORAGE_ROOT", str(mapping_env.storage_root))
    engine = create_engine(mapping_env.url)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection)
    set_local_tenant(
        db,
        mapping_env.store_id,
        mapping_env.user_id,
        "owner",
    )
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture()
def tenant(mapping_env: MappingEnv) -> TenantContext:
    return TenantContext(
        store_id=mapping_env.store_id,
        user_id=mapping_env.user_id,
        role="owner",
    )
