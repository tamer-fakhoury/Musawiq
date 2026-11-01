"""FR-0.6.5: password reset."""

from __future__ import annotations

from sqlalchemy import text

PASSWORD = "correct horse battery"
NEW_PASSWORD = "a completely new secret"


def _login(client, account, password=PASSWORD):
    return client.post(
        "/auth/login", json={"email": account.email, "password": password}
    )


def _forgot(client, email):
    return client.post("/auth/password/forgot", json={"email": email})


def test_forgot_always_returns_202_without_enumeration(client, account):
    known = _forgot(client, account.email)
    unknown = _forgot(client, "nobody@example.com")

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.json() == unknown.json() == {"status": "accepted"}


def test_reset_sets_password_and_token_is_single_use(
    client, account, monkeypatch
):
    raw = "reset-token-for-tests"
    monkeypatch.setattr(
        "musawiq.auth.password_reset.secrets.token_urlsafe",
        lambda _size: raw,
    )
    assert _forgot(client, account.email).status_code == 202

    reset = client.post(
        "/auth/password/reset",
        json={"token": raw, "password": NEW_PASSWORD},
    )
    assert reset.status_code == 200
    assert reset.json()["status"] == "password_reset"

    assert _login(client, account, PASSWORD).status_code == 401
    assert _login(client, account, NEW_PASSWORD).status_code == 200

    reuse = client.post(
        "/auth/password/reset",
        json={"token": raw, "password": "another new password"},
    )
    assert reuse.status_code == 422
    assert reuse.json()["error"]["code"] == "invalid_token"


def test_expired_reset_token_is_rejected(client, account, db_engine, monkeypatch):
    raw = "expired-reset-token"
    monkeypatch.setattr(
        "musawiq.auth.password_reset.secrets.token_urlsafe",
        lambda _size: raw,
    )
    assert _forgot(client, account.email).status_code == 202
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE email_verification_tokens "
                "SET expires_at = now() - interval '1 minute' "
                "WHERE purpose = 'password_reset'"
            )
        )

    response = client.post(
        "/auth/password/reset",
        json={"token": raw, "password": NEW_PASSWORD},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_token"


def test_password_reset_invalidates_previous_sessions(
    client, account, monkeypatch
):
    assert _login(client, account).status_code == 200
    old_session = client.cookies.get("msq_session")
    assert old_session

    raw = "session-reset-token"
    monkeypatch.setattr(
        "musawiq.auth.password_reset.secrets.token_urlsafe",
        lambda _size: raw,
    )
    assert _forgot(client, account.email).status_code == 202
    assert (
        client.post(
            "/auth/password/reset",
            json={"token": raw, "password": NEW_PASSWORD},
        ).status_code
        == 200
    )

    client.cookies.set("msq_session", old_session, path="/")
    assert client.get("/imports").status_code == 401
