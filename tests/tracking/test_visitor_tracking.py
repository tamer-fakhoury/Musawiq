"""FR-4.1.2: first-party page visit and interaction tracking."""

from __future__ import annotations

import uuid

from sqlalchemy import text

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def _create_session(client, site, *, ua=BROWSER_UA, consent="unknown", body=None):
    payload = {
        "consent_state": consent,
        "utm_source": "meta",
        "utm_medium": "paid_social",
        "utm_campaign": "coffee-launch",
        "tk": body,
    }
    return client.post(
        f"/p/{site.page_slug}/track/session",
        json=payload,
        headers={"User-Agent": ua, "Referer": "https://example.com/ad"},
    )


def _event(
    client,
    site,
    session_id,
    event_type="page_view",
    ua=BROWSER_UA,
    **extra,
):
    payload = {
        "session_id": session_id,
        "event_type": event_type,
        "event_id": str(uuid.uuid4()),
    }
    payload.update(extra)
    return client.post(
        f"/p/{site.page_slug}/track/events",
        json=payload,
        headers={"User-Agent": ua},
    )


def test_session_captures_attribution_and_hashed_ip(client, site, db_engine):
    response = _create_session(client, site)

    assert response.status_code == 201
    body = response.json()
    assert body["session_id"]
    assert response.cookies.get("msq_sid") == body["session_id"]
    assert body["attribution"]["utm_source"] == "meta"
    assert body["attribution"]["utm_campaign"] == "coffee-launch"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT ip_hash, user_agent, referrer, first_utm_source, "
                "first_utm_campaign, consent_state FROM tracking_sessions "
                "WHERE id = :id"
            ),
            {"id": body["session_id"]},
        ).mappings().one()
    assert len(row["ip_hash"]) == 64
    assert row["ip_hash"].isalnum()
    assert row["user_agent"] == BROWSER_UA
    assert row["referrer"] == "https://example.com/ad"
    assert row["first_utm_source"] == "meta"
    assert row["consent_state"] == "unknown"


def test_bot_traffic_is_flagged_and_excluded(client, site, db_engine):
    created = _create_session(client, site, ua=BOT_UA)
    assert created.status_code == 201
    assert created.json()["is_bot"] is True

    session_id = created.json()["session_id"]
    logged = _event(client, site, session_id, ua=BOT_UA)
    assert logged.status_code == 200
    assert logged.json()["is_bot"] is True

    with db_engine.connect() as conn:
        is_bot = conn.execute(
            text("SELECT is_bot FROM events WHERE tracking_session_id = :id"),
            {"id": session_id},
        ).scalar_one()
    assert is_bot is True


def test_consent_gates_non_essential_events(client, site, db_engine):
    created = _create_session(client, site, consent="unknown")
    session_id = created.json()["session_id"]

    view = _event(client, site, session_id, "page_view")
    assert view.status_code == 200

    blocked = _event(client, site, session_id, "cta_click")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "consent_required"

    granted = client.post(
        f"/p/{site.page_slug}/track/consent",
        json={"session_id": session_id, "consent_state": "granted"},
    )
    assert granted.status_code == 200
    assert granted.json()["consent_state"] == "granted"

    allowed = _event(client, site, session_id, "cta_click")
    assert allowed.status_code == 200

    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM events WHERE tracking_session_id = :id"
            ),
            {"id": session_id},
        ).scalar_one()
    assert count == 2


def test_unpublished_page_cannot_start_tracking(client, site):
    response = client.post(
        f"/p/{site.draft_slug}/track/session",
        json={"consent_state": "unknown"},
        headers={"User-Agent": BROWSER_UA},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "page_unavailable"


def test_first_party_script_is_served(client):
    response = client.get("/p/track.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "page_view" in response.text
    assert "cta_click" in response.text
    assert "cod_form_start" in response.text
    assert "event_id" in response.text


def test_duplicate_event_id_is_ignored_and_returns_original(
    client, site, db_engine
):
    created = _create_session(client, site, consent="granted")
    session_id = created.json()["session_id"]
    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "occurred_at": "2026-10-01T12:00:00Z",
    }

    first = _event(client, site, session_id, "product_view", **payload)
    assert first.status_code == 200
    assert first.json()["duplicate"] is False

    duplicate = _event(
        client,
        site,
        session_id,
        "product_view",
        **payload,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["accepted"] is True
    assert duplicate.json()["is_bot"] == first.json()["is_bot"]

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM events WHERE event_id = :id"),
            {"id": event_id},
        ).scalar_one()
    assert count == 1


def test_all_canonical_event_types_are_accepted(client, site, db_engine):
    created = _create_session(client, site, consent="granted")
    session_id = created.json()["session_id"]
    types = (
        "page_view",
        "product_view",
        "cta_click",
        "whatsapp_click",
        "cod_form_start",
        "cod_order_submitted",
        "deposit_confirmed",
    )
    for event_type in types:
        response = _event(
            client,
            site,
            session_id,
            event_type,
            event_id=str(uuid.uuid4()),
        )
        assert response.status_code == 200, response.text

    with db_engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT event_type FROM events "
                "WHERE tracking_session_id = :id ORDER BY event_type"
            ),
            {"id": session_id},
        ).scalars().all()
    assert stored == sorted(types)


def test_invalid_event_is_rejected_and_logged_without_payload(
    client, site, caplog
):
    created = _create_session(client, site, consent="granted")
    session_id = created.json()["session_id"]

    response = _event(
        client,
        site,
        session_id,
        "not_a_real_event",
        properties={"customer_email": "private@example.com"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_event_type"
    record = next(
        item
        for item in caplog.records
        if item.getMessage() == "event_rejected"
    )
    assert record.reason == "invalid_event_type"
    assert "private@example.com" not in caplog.text


def test_event_id_is_required(client, site):
    created = _create_session(client, site, consent="granted")
    session_id = created.json()["session_id"]

    response = client.post(
        f"/p/{site.page_slug}/track/events",
        json={"session_id": session_id, "event_type": "page_view"},
        headers={"User-Agent": BROWSER_UA},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_event_id"
