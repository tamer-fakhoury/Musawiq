"""Identity and tenancy tables: constraints and triggers (DB-0.4)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def _insert_user(conn, email="owner@example.com", role="owner", status="active"):
    return conn.execute(
        text(
            """
            INSERT INTO users (email, full_name, role, status)
            VALUES (:email, 'Test User', :role, :status)
            RETURNING id
            """
        ),
        {"email": email, "role": role, "status": status},
    ).scalar_one()


def _insert_store(conn, owner_user_id, slug="demo-store", onboarding_status="completed"):
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
                'USD', 'en', 'UTC', 'US', :onboarding_status
            )
            RETURNING id
            """
        ),
        {
            "owner_user_id": owner_user_id,
            "slug": slug,
            "onboarding_status": onboarding_status,
        },
    ).scalar_one()


def _insert_audit_log(conn):
    conn.execute(
        text(
            """
            INSERT INTO audit_logs (actor_type, action, target_type)
            VALUES ('system', 'test.action', 'test_target')
            """
        )
    )


def _insert_async_job(conn, idempotency_key=None):
    conn.execute(
        text(
            """
            INSERT INTO async_jobs (job_type, state, idempotency_key)
            VALUES ('import', 'queued', :idempotency_key)
            """
        ),
        {"idempotency_key": idempotency_key},
    )


def test_users_email_is_unique_case_insensitively(conn):
    _insert_user(conn, email="owner@example.com")

    with pytest.raises(DBAPIError):
        _insert_user(conn, email="OWNER@example.com")


def test_stores_slug_is_unique(conn):
    first_owner = _insert_user(conn, email="first@example.com")
    second_owner = _insert_user(conn, email="second@example.com")
    _insert_store(conn, first_owner, slug="same-slug")

    with pytest.raises(DBAPIError):
        _insert_store(conn, second_owner, slug="same-slug")


def test_one_store_per_owner(conn):
    owner = _insert_user(conn)
    _insert_store(conn, owner, slug="store-one")

    with pytest.raises(DBAPIError):
        _insert_store(conn, owner, slug="store-two")


def test_users_role_check(conn):
    with pytest.raises(DBAPIError):
        _insert_user(conn, role="admin")


def test_async_jobs_state_check(conn):
    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO async_jobs (job_type, state)
                VALUES ('import', 'paused')
                """
            )
        )


def test_stores_onboarding_status_check(conn):
    owner = _insert_user(conn)

    with pytest.raises(DBAPIError):
        _insert_store(conn, owner, onboarding_status="done")


def test_audit_logs_reject_update(conn):
    _insert_audit_log(conn)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE audit_logs SET action = 'changed'"))


def test_audit_logs_reject_delete(conn):
    _insert_audit_log(conn)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM audit_logs"))


def test_async_jobs_idempotency_key_is_unique(conn):
    _insert_async_job(conn, "same-key")

    with pytest.raises(DBAPIError):
        _insert_async_job(conn, "same-key")


def test_async_jobs_allows_multiple_null_idempotency_keys(conn):
    _insert_async_job(conn)
    _insert_async_job(conn)

    count = conn.execute(
        text("SELECT count(*) FROM async_jobs WHERE idempotency_key IS NULL")
    ).scalar_one()
    assert count == 2


def test_users_updated_at_is_touched(conn):
    user_id = conn.execute(
        text(
            """
            INSERT INTO users (email, full_name, role, status, updated_at)
            VALUES ('touch@example.com', 'Touch User', 'owner', 'active',
                    '2000-01-01T00:00:00Z')
            RETURNING id
            """
        )
    ).scalar_one()

    conn.execute(
        text("UPDATE users SET full_name = 'Changed User' WHERE id = :id"),
        {"id": user_id},
    )

    updated_at = conn.execute(
        text("SELECT updated_at FROM users WHERE id = :id"), {"id": user_id}
    ).scalar_one()
    assert updated_at > datetime(2000, 1, 1, tzinfo=timezone.utc)
