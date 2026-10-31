"""First-party landing-page visitor tracking (FR-4.1.2).

Bot rules (documented):
* user-agent contains a known crawler/bot token (see ``BOT_UA_PATTERNS``);
* more than ``RATE_LIMIT_SESSIONS`` sessions from one ``ip_hash`` within
  ``RATE_WINDOW_SECONDS`` are treated as automated traffic.

Bots are still recorded (event ``is_bot = true``) so they can be audited, and
are excluded from metrics by filtering on that flag. Only hashed IPs are stored.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, NoReturn

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("musawiq.events")

EVENT_TYPES = frozenset(
    {
        "page_view",
        "product_view",
        "cta_click",
        "whatsapp_click",
        "cod_form_start",
        "cod_order_submitted",
        "deposit_confirmed",
    }
)
ESSENTIAL_EVENTS = frozenset({"page_view"})
CONSENT_STATES = frozenset({"unknown", "granted", "denied"})
RATE_LIMIT_SESSIONS = 60
RATE_WINDOW_SECONDS = 60
BOT_UA_PATTERNS = re.compile(
    r"(bot|crawler|spider|slurp|bingpreview|facebookexternalhit|"
    r"headlesschrome|phantomjs|lighthouse|pingdom|uptime|"
    r"googlebot|bingbot|yandex|baidu|ahrefs|semrush|python-requests|"
    r"curl/|wget/|go-http-client)",
    re.IGNORECASE,
)
UTM_FIELDS = (
    "first_utm_source",
    "first_utm_medium",
    "first_utm_campaign",
    "first_utm_content",
    "first_utm_term",
)


class VisitorTrackingError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _reject(code: str, message: str, status_code: int = 422) -> NoReturn:
    logger.warning("event_rejected", extra={"reason": code})
    raise VisitorTrackingError(code, message, status_code=status_code)


def _parse_uuid(value: object, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        _reject(code, f"{code.removeprefix('invalid_')} must be a UUID.")


def _parse_occurred_at(value: object) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            _reject("invalid_occurred_at", "occurred_at must be an ISO datetime.")
    else:
        _reject("invalid_occurred_at", "occurred_at must be an ISO datetime.")
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _store_reference(
    session: Session,
    table: str,
    value: object,
    code: str,
    store_id: object,
) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    parsed = _parse_uuid(value, code)
    row = session.execute(
        text(
            f"SELECT 1 FROM {table} "
            "WHERE id = :id AND store_id = :store_id LIMIT 1"
        ),
        {"id": parsed, "store_id": store_id},
    ).first()
    if row is None:
        _reject(code, f"{code.removeprefix('invalid_')} is not valid for this store.")
    return parsed


def hash_ip(raw_ip: str | None) -> str:
    value = (raw_ip or "unknown").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_bot_user_agent(user_agent: str | None) -> bool:
    return bool(user_agent and BOT_UA_PATTERNS.search(user_agent))


def _store_config(session: Session, store_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT set_config('app.store_id', :value, true)"),
        {"value": str(store_id)},
    )


def _published_page(session: Session, slug: str):
    row = session.execute(
        text(
            "SELECT id, store_id, test_id, language, published_url "
            "FROM landing_pages "
            "WHERE slug = :slug AND status = 'published' AND deleted_at IS NULL"
        ),
        {"slug": slug},
    ).mappings().one_or_none()
    if row is None:
        raise VisitorTrackingError(
            "page_unavailable", "This page is unavailable.", status_code=404
        )
    _store_config(session, row["store_id"])
    return row


def _campaign_from_token(session: Session, store_id, token: str | None):
    if not token:
        return None, {}
    row = session.execute(
        text(
            "SELECT campaign_id, utm_source, utm_medium, utm_campaign, "
            "utm_content, utm_term FROM tracking_links "
            "WHERE token = :token AND store_id = :store_id"
        ),
        {"token": token, "store_id": store_id},
    ).mappings().one_or_none()
    if row is None:
        return None, {}
    return row["campaign_id"], {
        "first_utm_source": row["utm_source"],
        "first_utm_medium": row["utm_medium"],
        "first_utm_campaign": row["utm_campaign"],
        "first_utm_content": row["utm_content"],
        "first_utm_term": row["utm_term"],
    }


def create_session(
    session: Session,
    slug: str,
    payload: Mapping[str, Any],
    *,
    user_agent: str | None,
    ip_hash: str,
    referrer: str | None = None,
) -> dict[str, Any]:
    page = _published_page(session, slug)
    campaign_id, utm = _campaign_from_token(
        session, page["store_id"], payload.get("tk")
    )
    for field in UTM_FIELDS:
        supplied = payload.get(field)
        if supplied is None:
            supplied = payload.get(field.replace("first_", ""))
        if supplied is not None:
            utm[field] = str(supplied)

    consent = payload.get("consent_state", "unknown")
    if consent not in CONSENT_STATES:
        raise VisitorTrackingError(
            "invalid_consent", "consent_state must be unknown, granted, or denied."
        )

    recent = session.execute(
        text(
            "SELECT count(*) FROM tracking_sessions "
            "WHERE store_id = :store_id AND ip_hash = :ip_hash "
            "AND started_at > now() - make_interval(secs => :window)"
        ),
        {
            "store_id": page["store_id"],
            "ip_hash": ip_hash,
            "window": RATE_WINDOW_SECONDS,
        },
    ).scalar_one()
    bot = is_bot_user_agent(user_agent) or recent >= RATE_LIMIT_SESSIONS

    session_id = session.execute(
        text(
            """
            INSERT INTO tracking_sessions (
                store_id, landing_page_id, test_id, campaign_id,
                first_utm_source, first_utm_medium, first_utm_campaign,
                first_utm_content, first_utm_term, referrer, user_agent,
                ip_hash, consent_state, started_at, last_seen_at
            ) VALUES (
                :store_id, :landing_page_id, :test_id, :campaign_id,
                :first_utm_source, :first_utm_medium, :first_utm_campaign,
                :first_utm_content, :first_utm_term, :referrer, :user_agent,
                :ip_hash, :consent_state, now(), now()
            )
            RETURNING id
            """
        ),
        {
            "store_id": page["store_id"],
            "landing_page_id": page["id"],
            "test_id": page["test_id"],
            "campaign_id": campaign_id,
            "first_utm_source": utm.get("first_utm_source"),
            "first_utm_medium": utm.get("first_utm_medium"),
            "first_utm_campaign": utm.get("first_utm_campaign"),
            "first_utm_content": utm.get("first_utm_content"),
            "first_utm_term": utm.get("first_utm_term"),
            "referrer": referrer,
            "user_agent": (user_agent or "unknown")[:1000],
            "ip_hash": ip_hash,
            "consent_state": consent,
        },
    ).scalar_one()
    return {
        "session_id": str(session_id),
        "consent_state": consent,
        "is_bot": bot,
        "campaign_id": str(campaign_id) if campaign_id else None,
        "attribution": {
            "utm_source": utm.get("first_utm_source"),
            "utm_medium": utm.get("first_utm_medium"),
            "utm_campaign": utm.get("first_utm_campaign"),
            "utm_content": utm.get("first_utm_content"),
            "utm_term": utm.get("first_utm_term"),
        },
    }


def set_consent(
    session: Session, slug: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    page = _published_page(session, slug)
    state = payload.get("consent_state")
    if state not in CONSENT_STATES:
        raise VisitorTrackingError(
            "invalid_consent", "consent_state must be unknown, granted, or denied."
        )
    row = _session_row(session, page["store_id"], payload.get("session_id"))
    session.execute(
        text(
            "UPDATE tracking_sessions SET consent_state = :state, "
            "last_seen_at = now() WHERE id = :id AND store_id = :store_id"
        ),
        {"state": state, "id": row["id"], "store_id": page["store_id"]},
    )
    return {"session_id": str(row["id"]), "consent_state": state}


def _session_row(session: Session, store_id, session_id: object):
    try:
        session_uuid = uuid.UUID(str(session_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise VisitorTrackingError(
            "invalid_session", "session_id is required.", status_code=400
        ) from exc
    row = session.execute(
        text(
            "SELECT * FROM tracking_sessions "
            "WHERE id = :id AND store_id = :store_id"
        ),
        {"id": session_uuid, "store_id": store_id},
    ).mappings().one_or_none()
    if row is None:
        raise VisitorTrackingError(
            "session_not_found", "Tracking session not found.", status_code=404
        )
    return row


def ingest_event(
    session: Session,
    slug: str,
    payload: Mapping[str, Any],
    *,
    user_agent: str | None,
    ip_hash: str,
    referrer: str | None = None,
) -> dict[str, Any]:
    page = _published_page(session, slug)
    row = _session_row(session, page["store_id"], payload.get("session_id"))

    event_type = payload.get("event_type")
    if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
        _reject(
            "invalid_event_type",
            "event_type must be a canonical event type.",
        )
    active = session.execute(
        text(
            "SELECT 1 FROM event_types "
            "WHERE code = :code AND is_active LIMIT 1"
        ),
        {"code": event_type},
    ).first()
    if active is None:
        _reject("invalid_event_type", "event_type is not active.")
    if (
        event_type not in ESSENTIAL_EVENTS
        and row["consent_state"] != "granted"
    ):
        _reject(
            "consent_required",
            "Consent is required before non-essential tracking.",
            status_code=403,
        )

    event_id = payload.get("event_id")
    if event_id in (None, ""):
        _reject("invalid_event_id", "event_id is required.")
    event_uuid = _parse_uuid(event_id, "invalid_event_id")
    occurred_at = _parse_occurred_at(payload.get("occurred_at"))

    bot = is_bot_user_agent(user_agent)
    properties = payload.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        _reject("invalid_properties", "properties must be an object.")
    props = dict(properties or {})
    props.setdefault("schema_version", 1)

    store_id = page["store_id"]
    product_id = _store_reference(
        session, "products", payload.get("product_id"), "invalid_product_id", store_id
    )
    adset_id = _store_reference(
        session, "ad_sets", payload.get("adset_id"), "invalid_adset_id", store_id
    )
    ad_variation_id = _store_reference(
        session,
        "ad_variations",
        payload.get("ad_variation_id"),
        "invalid_ad_variation_id",
        store_id,
    )

    inserted = session.execute(
        text(
            """
            INSERT INTO events (
                store_id, event_id, tracking_session_id, test_id, product_id,
                campaign_id, adset_id, ad_variation_id, event_type, source,
                url, referrer, occurred_at, is_bot, properties
            ) VALUES (
                :store_id, :event_id, :session_id, :test_id, :product_id,
                :campaign_id, :adset_id, :ad_variation_id, :event_type, 'web',
                :url, :referrer, :occurred_at, :is_bot, :properties
            )
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id, is_bot
            """
        ),
        {
            "store_id": store_id,
            "event_id": event_uuid,
            "session_id": row["id"],
            "test_id": row["test_id"],
            "product_id": product_id,
            "campaign_id": row["campaign_id"],
            "adset_id": adset_id,
            "ad_variation_id": ad_variation_id,
            "event_type": event_type,
            "url": payload.get("url"),
            "referrer": referrer or row["referrer"],
            "occurred_at": occurred_at,
            "is_bot": bot,
            "properties": Jsonb(props),
        },
    ).mappings().one_or_none()
    session.execute(
        text("UPDATE tracking_sessions SET last_seen_at = now() WHERE id = :id"),
        {"id": row["id"]},
    )
    if inserted is None:
        original = session.execute(
            text(
                "SELECT is_bot FROM events "
                "WHERE event_id = :event_id AND store_id = :store_id"
            ),
            {"event_id": event_uuid, "store_id": store_id},
        ).mappings().one_or_none()
        return {
            "event_id": str(event_uuid),
            "accepted": True,
            "duplicate": True,
            "is_bot": original["is_bot"] if original is not None else None,
        }
    return {
        "event_id": str(event_uuid),
        "accepted": True,
        "duplicate": False,
        "is_bot": inserted["is_bot"],
    }


def first_party_script() -> str:
    return """(function () {
  var base = '/p/' + document.documentElement.dataset.msqSlug + '/track';
  function cookie(name) {
    return document.cookie.split('; ').find(function (row) {
      return row.indexOf(name + '=') === 0;
    });
  }
  function consent() {
    var row = cookie('msq_consent');
    return row ? decodeURIComponent(row.split('=')[1]) : 'unknown';
  }
  function session() {
    return fetch(base + '/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        consent_state: consent(),
        tk: new URLSearchParams(location.search).get('tk')
      })
    }).then(function (response) { return response.json(); });
  }
  function eventId() {
    if (window.crypto && crypto.randomUUID) { return crypto.randomUUID(); }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }
  function track(sid, type, extra) {
    return fetch(base + '/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({
        session_id: sid, event_type: type, event_id: eventId(),
        url: location.href
      }, extra || {}))
    });
  }
  session().then(function (data) {
    var sid = data.session_id;
    track(sid, 'page_view');
    document.querySelectorAll('[data-msq-product]').forEach(function (node) {
      var seen = false;
      new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting && !seen) {
            seen = true;
            track(sid, 'product_view');
          }
        });
      }).observe(node);
    });
    document.addEventListener('click', function (event) {
      var target = event.target.closest('[data-msq-cta]');
      if (target) { track(sid, 'cta_click'); }
    });
    document.addEventListener('focusin', function (event) {
      if (event.target.closest('[data-msq-cod-form]')) {
        track(sid, 'cod_form_start');
      }
    }, { once: true });
  });
})();"""


__all__ = [
    "BOT_UA_PATTERNS",
    "CONSENT_STATES",
    "ESSENTIAL_EVENTS",
    "EVENT_TYPES",
    "RATE_LIMIT_SESSIONS",
    "RATE_WINDOW_SECONDS",
    "VisitorTrackingError",
    "create_session",
    "first_party_script",
    "hash_ip",
    "ingest_event",
    "is_bot_user_agent",
    "set_consent",
]
