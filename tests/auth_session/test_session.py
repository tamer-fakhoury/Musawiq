"""FR-0.6.4: cookie tenant resolution and CSRF enforcement."""

from __future__ import annotations

from sqlalchemy import text

PASSWORD = "correct horse battery"


def _login(client, account):
    return client.post(
        "/auth/login",
        json={"email": account.email, "password": PASSWORD},
    )


def _csrf(client) -> str:
    return client.cookies.get("msq_csrf")


def test_cookie_session_resolves_tenant_from_database(client, account):
    login = _login(client, account)
    assert login.status_code == 200
    assert client.cookies.get("msq_session")
    assert _csrf(client)

    response = client.get("/imports")

    assert response.status_code == 200
    assert response.json() == []


def test_unauthenticated_requests_are_rejected(client):
    response = client.get("/imports")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_role_is_read_from_database_per_request(client, account, db_engine):
    assert _login(client, account).status_code == 200
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET role = 'analyst' WHERE id = :id"),
            {"id": account.user_id},
        )

    from musawiq.auth.errors import PermissionDenied

    try:
        response = client.put(
            "/store/profile",
            json={"category_ids": []},
            headers={"X-CSRF-Token": _csrf(client)},
        )
    except PermissionDenied:
        return
    assert response.status_code == 403


def test_state_changing_requests_require_csrf(client, account):
    assert _login(client, account).status_code == 200

    blocked = client.put(
        "/store/profile", json={"category_ids": []}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_invalid"

    allowed = client.put(
        "/store/profile",
        json={"category_ids": []},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert allowed.status_code == 422
    assert allowed.json()["error"]["code"] == "category_required"


def test_tampered_session_cookie_is_rejected(client, account):
    assert _login(client, account).status_code == 200
    client.cookies.delete("msq_session")
    client.cookies.set(
        "msq_session", "tampered.value", domain="testserver", path="/"
    )

    response = client.get("/imports")

    assert response.status_code == 401
