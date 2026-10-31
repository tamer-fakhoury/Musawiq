"""COD order submission with market validation, spam and dedupe (FR-4.1.4)."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.security.crypto import encrypt_secret

PHONE_RULES = {
    "SA": re.compile(r"^(?:\+9665|05)\d{8}$"),
    "AE": re.compile(r"^(?:\+9715|05)\d{8}$"),
    "EG": re.compile(r"^(?:\+201|01)\d{9}$"),
    "US": re.compile(r"^\+1\d{10}$"),
}
DEFAULT_PHONE_RULE = re.compile(r"^\+?\d{8,15}$")
ADDRESS_MIN = {"SA": 10, "AE": 10, "EG": 10, "US": 8}
DEFAULT_ADDRESS_MIN = 5
MIN_FILL_SECONDS = 2
RATE_LIMIT_ORDERS = 5
RATE_WINDOW_SECONDS = 600
DEDUPE_WINDOW_SECONDS = 600


class CodOrderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class CodFieldError(CodOrderError):
    def __init__(self, fields: dict[str, str]) -> None:
        self.fields = fields
        super().__init__(
            "validation_error", "Some fields need attention.", status_code=422
        )


class DuplicateOrderError(CodOrderError):
    def __init__(self, order_id: uuid.UUID) -> None:
        self.order_id = order_id
        super().__init__(
            "duplicate_order",
            "This order was already submitted.",
            status_code=409,
        )


class RateLimitService:
    """Minimal fixed-window rate limiter backed by the orders table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def check_limit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        count = self.session.execute(
            text(
                """
                SELECT count(*) FROM orders AS o
                LEFT JOIN tracking_sessions AS ts
                    ON ts.id = o.tracking_session_id
                WHERE o.store_id = :store_id
                  AND o.origin = 'cod'
                  AND o.placed_at > now() - make_interval(secs => :window)
                  AND (
                      ts.ip_hash = :key
                      OR o.customer_phone = :key
                  )
                """
            ),
            {
                "store_id": self.store_id,
                "window": window_seconds,
                "key": key,
            },
        ).scalar_one()
        return count < limit

    def bind(self, store_id: uuid.UUID) -> "RateLimitService":
        self.store_id = store_id
        return self


def _store_config(session: Session, store_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT set_config('app.store_id', :value, true)"),
        {"value": str(store_id)},
    )


def _published_page(session: Session, slug: str):
    row = session.execute(
        text(
            """
            SELECT lp.id, lp.store_id, lp.test_id, lp.currency,
                   pv.content
            FROM landing_pages AS lp
            LEFT JOIN page_versions AS pv ON pv.id = lp.published_version_id
            WHERE lp.slug = :slug AND lp.status = 'published'
              AND lp.deleted_at IS NULL
            """
        ),
        {"slug": slug},
    ).mappings().one_or_none()
    if row is None:
        raise CodOrderError(
            "page_unavailable", "This page is unavailable.", status_code=404
        )
    _store_config(session, row["store_id"])
    return row


def _session_row(session: Session, store_id, session_id: object):
    if session_id is None:
        return None
    try:
        session_uuid = uuid.UUID(str(session_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CodFieldError({"session_id": "invalid session id"}) from exc
    row = session.execute(
        text(
            "SELECT * FROM tracking_sessions "
            "WHERE id = :id AND store_id = :store_id"
        ),
        {"id": session_uuid, "store_id": store_id},
    ).mappings().one_or_none()
    if row is None:
        raise CodFieldError({"session_id": "unknown tracking session"})
    return row


def _market(content: Mapping[str, Any] | None, store_country: str) -> str:
    content = content or {}
    product = content.get("product") or {}
    return str(
        content.get("target_market")
        or product.get("target_market")
        or store_country
    )


def _validated_fields(
    payload: Mapping[str, Any], market: str
) -> dict[str, Any]:
    errors: dict[str, str] = {}

    name = payload.get("customer_name")
    if not isinstance(name, str) or not name.strip():
        errors["customer_name"] = "name is required"
    elif len(name.strip()) > 120:
        errors["customer_name"] = "name is too long"

    phone = payload.get("customer_phone")
    clean_phone = re.sub(r"[\s()-]", "", str(phone or ""))
    rule = PHONE_RULES.get(market, DEFAULT_PHONE_RULE)
    if not rule.fullmatch(clean_phone):
        errors["customer_phone"] = f"phone does not match {market} format"

    address = payload.get("customer_address")
    minimum = ADDRESS_MIN.get(market, DEFAULT_ADDRESS_MIN)
    if not isinstance(address, str) or len(address.strip()) < minimum:
        errors["customer_address"] = (
            f"address must be at least {minimum} characters"
        )
    elif len(address.strip()) > 500:
        errors["customer_address"] = "address is too long"

    quantity = payload.get("quantity", 1)
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or not 1 <= quantity <= 100
    ):
        errors["quantity"] = "quantity must be between 1 and 100"

    for key, limit in (("variant", 120), ("notes", 500)):
        value = payload.get(key)
        if value is not None and (
            not isinstance(value, str) or len(value) > limit
        ):
            errors[key] = f"{key} must be a string up to {limit} characters"

    if errors:
        raise CodFieldError(errors)
    return {
        "customer_name": name.strip(),
        "customer_phone": clean_phone,
        "customer_address": address.strip(),
        "quantity": quantity,
        "variant": payload.get("variant"),
        "notes": payload.get("notes"),
    }


def _check_spam(payload: Mapping[str, Any]) -> None:
    if str(payload.get("website") or "").strip():
        raise CodOrderError(
            "spam_detected", "Submission rejected as spam.", status_code=422
        )
    started = payload.get("form_started_at")
    if started is None:
        return
    try:
        started_at = dt.datetime.fromisoformat(str(started).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CodFieldError(
            {"form_started_at": "invalid timestamp"}
        ) from exc
    now = dt.datetime.now(dt.timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=dt.timezone.utc)
    elapsed = (now - started_at).total_seconds()
    if elapsed < MIN_FILL_SECONDS or elapsed > 86400:
        raise CodOrderError(
            "spam_detected", "Submission rejected as spam.", status_code=422
        )


def _bucket(now: dt.datetime) -> int:
    return int(now.timestamp()) // DEDUPE_WINDOW_SECONDS


def submit_cod_order(
    session: Session,
    slug: str,
    payload: Mapping[str, Any],
    *,
    user_agent: str | None = None,
) -> dict[str, Any]:
    page = _published_page(session, slug)
    store_country = session.execute(
        text("SELECT country_code FROM stores WHERE id = :id"),
        {"id": page["store_id"]},
    ).scalar_one()
    content = page["content"] or {}
    market = _market(content, store_country)
    tracking = _session_row(session, page["store_id"], payload.get("session_id"))

    _check_spam(payload)
    fields = _validated_fields(payload, market)

    limiter = RateLimitService(session).bind(page["store_id"])
    rate_key = tracking["ip_hash"] if tracking else fields["customer_phone"]
    if not limiter.check_limit(
        rate_key, limit=RATE_LIMIT_ORDERS, window_seconds=RATE_WINDOW_SECONDS
    ):
        raise CodOrderError(
            "rate_limited", "Too many orders. Try again later.", status_code=429
        )

    product = content.get("product") or {}
    product_name = product.get("name") or content.get("name") or "Product"
    price_minor = int(product.get("price_minor") or 0)
    currency = (product.get("currency") or page["currency"]).strip()
    total_minor = price_minor * fields["quantity"]

    product_id = payload.get("product_id")
    if product_id is not None:
        try:
            product_uuid = uuid.UUID(str(product_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise CodFieldError({"product_id": "invalid product id"}) from exc
        exists = session.execute(
            text(
                "SELECT 1 FROM products WHERE id = :id AND store_id = :store_id"
            ),
            {"id": product_uuid, "store_id": page["store_id"]},
        ).scalar_one_or_none()
        if exists is None:
            raise CodFieldError({"product_id": "unknown product"})
        payload = {**payload, "product_id": str(product_uuid)}
    else:
        payload = {**payload, "product_id": None}

    now = dt.datetime.now(dt.timezone.utc)
    dedupe_source = "|".join(
        [
            str(tracking["id"]) if tracking else "anon",
            str(payload.get("product_id") or product_name),
            str(fields["quantity"]),
            fields["customer_phone"],
            str(total_minor),
            str(fields["variant"] or ""),
            str(_bucket(now)),
        ]
    )
    dedupe_hash = hashlib.sha256(dedupe_source.encode("utf-8")).hexdigest()

    order_id = session.execute(
        text(
            """
            INSERT INTO orders (
                store_id, origin, test_id, test_phase, status, currency,
                total_minor, customer_name, customer_phone,
                customer_address_enc, landing_page_id, campaign_id,
                tracking_session_id, dedupe_hash, placed_at
            ) VALUES (
                :store_id, 'cod', :test_id, 'during_test', 'pending', :currency,
                :total_minor, :customer_name, :customer_phone,
                :customer_address_enc, :landing_page_id, :campaign_id,
                :tracking_session_id, :dedupe_hash, :placed_at
            )
            ON CONFLICT (store_id, dedupe_hash) WHERE dedupe_hash IS NOT NULL
            DO NOTHING
            RETURNING id
            """
        ),
        {
            "store_id": page["store_id"],
            "test_id": page["test_id"],
            "currency": currency,
            "total_minor": total_minor,
            "customer_name": fields["customer_name"],
            "customer_phone": fields["customer_phone"],
            "customer_address_enc": (
                encrypt_secret(fields["customer_address"]) or ""
            ).encode("ascii"),
            "landing_page_id": page["id"],
            "campaign_id": tracking["campaign_id"] if tracking else None,
            "tracking_session_id": tracking["id"] if tracking else None,
            "dedupe_hash": dedupe_hash,
            "placed_at": now,
        },
    ).scalar_one_or_none()

    if order_id is None:
        existing = session.execute(
            text(
                "SELECT id FROM orders "
                "WHERE store_id = :store_id AND dedupe_hash = :dedupe_hash"
            ),
            {"store_id": page["store_id"], "dedupe_hash": dedupe_hash},
        ).scalar_one()
        raise DuplicateOrderError(existing)

    session.execute(
        text(
            """
            INSERT INTO order_items (
                store_id, order_id, product_id, product_name_snapshot,
                quantity, unit_price_minor, line_total_minor, currency, metadata
            ) VALUES (
                :store_id, :order_id, :product_id, :product_name,
                :quantity, :unit_price_minor, :line_total_minor, :currency,
                :metadata
            )
            """
        ),
        {
            "store_id": page["store_id"],
            "order_id": order_id,
            "product_id": payload.get("product_id"),
            "product_name": product_name,
            "quantity": fields["quantity"],
            "unit_price_minor": price_minor,
            "line_total_minor": total_minor,
            "currency": currency,
            "metadata": Jsonb(
                {
                    "schema_version": 1,
                    "variant": fields["variant"],
                    "notes": fields["notes"],
                }
            ),
        },
    )
    if tracking is not None:
        session.execute(
            text(
                "UPDATE tracking_sessions SET last_seen_at = now() WHERE id = :id"
            ),
            {"id": tracking["id"]},
        )
    return {
        "order_id": str(order_id),
        "status": "pending",
        "origin": "cod",
        "test_phase": "during_test",
        "currency": currency,
        "quantity": fields["quantity"],
        "total_minor": total_minor,
        "duplicate": False,
    }


__all__ = [
    "ADDRESS_MIN",
    "CodFieldError",
    "CodOrderError",
    "DEFAULT_ADDRESS_MIN",
    "DEFAULT_PHONE_RULE",
    "DuplicateOrderError",
    "MIN_FILL_SECONDS",
    "PHONE_RULES",
    "RATE_LIMIT_ORDERS",
    "RATE_WINDOW_SECONDS",
    "RateLimitService",
    "submit_cod_order",
]
