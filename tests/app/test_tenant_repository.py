"""Tenant context and repository isolation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from musawiq.db.tenant import (
    TenantContext,
    TenantContextError,
    get_tenant,
    set_local_tenant,
)
from musawiq.repositories.base import TenantScopeError, TenantScopedRepository


def _probe_table(session, name: str) -> None:
    session.execute(
        text(
            f"""
            CREATE TABLE public.{name} (
                id uuid PRIMARY KEY DEFAULT uuidv7(),
                store_id uuid NOT NULL,
                name text NOT NULL
            )
            """
        )
    )


def test_set_local_tenant_sets_transaction_settings(db_session) -> None:
    store_id = uuid.uuid4()
    user_id = uuid.uuid4()

    context = set_local_tenant(db_session, store_id, user_id)

    assert context == TenantContext(store_id=store_id, user_id=user_id)
    assert get_tenant(db_session) == context
    row = db_session.execute(
        text(
            "SELECT current_setting('app.store_id'), "
            "current_setting('app.user_id')"
        )
    ).one()
    assert row == (str(store_id), str(user_id))


def test_repository_requires_a_tenant_context(db_session) -> None:
    table = f"repo_probe_{uuid.uuid4().hex[:8]}"
    _probe_table(db_session, table)

    with pytest.raises(TenantContextError):
        TenantScopedRepository(db_session, table)


def test_repository_is_tenant_scoped(db_session) -> None:
    table = f"repo_probe_{uuid.uuid4().hex[:8]}"
    _probe_table(db_session, table)

    store_a = uuid.uuid4()
    store_b = uuid.uuid4()
    user_id = uuid.uuid4()

    set_local_tenant(db_session, store_a, user_id)
    repository = TenantScopedRepository(db_session, table)

    created = repository.insert({"name": "alpha"})
    assert uuid.UUID(str(created["store_id"])) == store_a

    fetched = repository.get(created["id"])
    assert fetched is not None
    assert fetched["name"] == "alpha"

    listed = repository.list()
    assert [row["name"] for row in listed] == ["alpha"]

    filtered = repository.list(filters={"name": "alpha"})
    assert len(filtered) == 1
    assert repository.list(filters={"name": "missing"}) == []

    updated = repository.update(created["id"], {"name": "beta"})
    assert updated is not None
    assert updated["name"] == "beta"

    with pytest.raises(TenantScopeError):
        repository.insert({"store_id": store_b, "name": "cross-tenant"})

    set_local_tenant(db_session, store_b, user_id)
    other_tenant = TenantScopedRepository(db_session, table)

    assert other_tenant.list() == []
    assert other_tenant.get(created["id"]) is None
    assert other_tenant.delete(created["id"]) is False

    set_local_tenant(db_session, store_a, user_id)
    own_tenant = TenantScopedRepository(db_session, table)

    assert own_tenant.delete(created["id"]) is True
    assert own_tenant.get(created["id"]) is None
