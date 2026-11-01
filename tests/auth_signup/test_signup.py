"""FR-0.6.1: account signup."""

from __future__ import annotations

import json

from sqlalchemy import text

PASSWORD = "correct horse battery"


def _signup(client, email, password=PASSWORD):
    return client.post(
        "/auth/signup", json={"email": email, "password": password}
    )


def test_signup_hashes_password_queues_verification_and_returns_201(
    client, db_engine
):
    response = _signup(client, "Merchant@Example.com")

    assert response.status_code == 201
    assert response.json() == {"status": "pending_verification"}
    assert "password" not in response.text.lower()
    assert "argon2" not in response.text.lower()

    with db_engine.connect() as conn:
        user = conn.execute(
            text(
                "SELECT id, email, password_hash, status, email_verified_at "
                "FROM users WHERE email = :email"
            ),
            {"email": "merchant@example.com"},
        ).mappings().one()
        job = conn.execute(
            text(
                "SELECT job_type, state, payload FROM async_jobs "
                "WHERE job_type = 'email_verification'"
            )
        ).mappings().one()

    assert str(user["email"]) == "merchant@example.com"
    assert user["password_hash"].startswith("$argon2id$")
    assert PASSWORD not in user["password_hash"]
    assert user["status"] == "invited"
    assert user["email_verified_at"] is None

    assert job["job_type"] == "email_verification"
    assert job["state"] == "queued"
    payload = job["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["user_id"] == str(user["id"])
    assert payload["email"] == "merchant@example.com"


def test_duplicate_email_returns_generic_conflict(client, db_engine):
    assert _signup(client, "dupe@example.com").status_code == 201

    duplicate = _signup(client, "DUPE@example.com")

    assert duplicate.status_code == 409
    error = duplicate.json()["error"]
    assert error["code"] == "signup_failed"
    lowered = error["message"].lower()
    assert "exist" not in lowered
    assert "duplicate" not in lowered
    assert "already" not in lowered

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM users WHERE email = 'dupe@example.com'")
        ).scalar_one()
    assert count == 1


def test_weak_password_is_rejected_without_creating_user(client, db_engine):
    response = _signup(client, "weak@example.com", password="shortpass12")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"
    assert "shortpass12" not in response.text

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM users WHERE email = 'weak@example.com'")
        ).scalar_one()
    assert count == 0


def test_invalid_email_is_rejected(client):
    response = _signup(client, "not-an-email")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_email"
