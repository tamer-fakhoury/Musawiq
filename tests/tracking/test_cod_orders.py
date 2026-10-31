"""FR-4.1.4: COD order form validation, dedupe, spam, and rate limits."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _session(client, site):
    response = client.post(
        f"/p/{site.page_slug}/track/session",
        json={"consent_state": "granted", "tk": site.tracking_token},
        headers={"User-Agent": UA},
    )
    assert response.status_code == 201
    return response.json()["session_id"]


def _payload(session_id, **overrides):
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=10)
    payload = {
        "session_id": session_id,
        "customer_name": "Ahmed Ali",
        "customer_phone": "0512345678",
        "customer_address": "Riyadh, Al Olaya, King Fahd Road 12",
        "quantity": 1,
        "variant": "Black",
        "notes": "Call before delivery",
        "form_started_at": started.isoformat(),
    }
    payload.update(overrides)
    return payload


def _submit(client, site, payload):
    return client.post(
        f"/p/{site.page_slug}/cod-orders",
        json=payload,
        headers={"User-Agent": UA},
    )


def test_valid_order_is_stored_and_linked(client, site, db_engine):
    session_id = _session(client, site)

    response = _submit(
        client,
        site,
        _payload(session_id, quantity=2),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["origin"] == "cod"
    assert body["test_phase"] == "during_test"
    assert body["quantity"] == 2
    assert body["total_minor"] == 10000

    with db_engine.connect() as conn:
        order = conn.execute(
            text(
                """
                SELECT origin, status, test_phase, currency, total_minor,
                       customer_name, customer_phone, customer_address_enc,
                       landing_page_id, campaign_id, tracking_session_id,
                       dedupe_hash
                FROM orders WHERE id = :id
                """
            ),
            {"id": body["order_id"]},
        ).mappings().one()
        item = conn.execute(
            text(
                "SELECT quantity, unit_price_minor, line_total_minor, "
                "product_name_snapshot FROM order_items WHERE order_id = :id"
            ),
            {"id": body["order_id"]},
        ).mappings().one()

    assert order["origin"] == "cod"
    assert order["status"] == "pending"
    assert order["test_phase"] == "during_test"
    assert order["currency"] == "USD"
    assert order["total_minor"] == 10000
    assert order["campaign_id"] is not None
    assert order["tracking_session_id"] is not None
    assert len(order["dedupe_hash"]) == 64
    ciphertext = bytes(order["customer_address_enc"])
    assert b"Riyadh" not in ciphertext

    assert item["quantity"] == 2
    assert item["unit_price_minor"] == 5000
    assert item["line_total_minor"] == 10000
    assert item["product_name_snapshot"] == "Tracked Product"


def test_invalid_fields_return_field_level_errors(client, site, db_engine):
    session_id = _session(client, site)

    response = _submit(
        client,
        site,
        _payload(
            session_id,
            customer_phone="123",
            customer_address="x",
            quantity=0,
        ),
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert set(error["fields"]) == {
        "customer_phone",
        "customer_address",
        "quantity",
    }

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM orders WHERE store_id = :id"),
            {"id": site.store_id},
        ).scalar_one()
    assert count == 0


def test_duplicate_submission_is_guarded(client, site):
    session_id = _session(client, site)
    payload = _payload(session_id)

    first = _submit(client, site, payload)
    second = _submit(client, site, payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_order"
    assert second.json()["order_id"] == first.json()["order_id"]


def test_spam_heuristics_and_rate_limit_apply(client, site):
    session_id = _session(client, site)

    honeypot = _submit(client, site, _payload(session_id, website="spam-bot"))
    assert honeypot.status_code == 422
    assert honeypot.json()["error"]["code"] == "spam_detected"

    instant = _submit(
        client,
        site,
        _payload(
            session_id,
            form_started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    assert instant.status_code == 422
    assert instant.json()["error"]["code"] == "spam_detected"

    for quantity in range(1, 6):
        accepted = _submit(client, site, _payload(session_id, quantity=quantity))
        assert accepted.status_code == 201, accepted.text

    blocked = _submit(client, site, _payload(session_id, quantity=6))
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
