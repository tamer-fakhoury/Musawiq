"""Campaign tracking links and publication tracking checks (FR-3.2.4)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.landing_pages import PUBLIC_BASE_URL

REQUIRED_UTM = ("utm_source", "utm_medium", "utm_campaign")
DEFAULT_UTM = {
    "utm_source": "musawiq",
    "utm_medium": "paid_social",
}


class TrackingError(Exception):
    """Base class for tracking link failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TrackingError(f"invalid_{name}", f"{name} must be a UUID.") from exc


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "campaign"


def _campaign(session: Session, tenant: TenantContext, campaign_id: object):
    campaign_uuid = _uuid(campaign_id, "campaign_id")
    row = session.execute(
        text(
            """
            SELECT c.*, t.product_concept_id, pc.name AS product_name
            FROM campaigns AS c
            JOIN tests AS t ON t.id = c.test_id
            JOIN product_concepts AS pc ON pc.id = t.product_concept_id
            WHERE c.id = :id AND c.store_id = :store_id
            """
        ),
        {"id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise TrackingError("not_found", "Campaign not found.", status_code=404)
    return row


def _landing_page(
    session: Session,
    tenant: TenantContext,
    campaign: Mapping[str, Any],
    landing_page_id: object,
):
    if landing_page_id is None:
        rows = session.execute(
            text(
                """
                SELECT * FROM landing_pages
                WHERE test_id = :test_id AND store_id = :store_id
                  AND deleted_at IS NULL
                ORDER BY created_at, id
                """
            ),
            {"test_id": campaign["test_id"], "store_id": tenant.store_id},
        ).mappings().all()
        if len(rows) != 1:
            raise TrackingError(
                "landing_page_required",
                "Campaign must link to exactly one landing page.",
            )
        return rows[0]
    page_uuid = _uuid(landing_page_id, "landing_page_id")
    row = session.execute(
        text(
            """
            SELECT * FROM landing_pages
            WHERE id = :id AND store_id = :store_id AND deleted_at IS NULL
            """
        ),
        {"id": page_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None or row["test_id"] != campaign["test_id"]:
        raise TrackingError(
            "invalid_landing_page",
            "Landing page must belong to the campaign's product test.",
        )
    return row


def _post(session: Session, tenant: TenantContext, post_id: object):
    post_uuid = _uuid(post_id, "post_id")
    row = session.execute(
        text("SELECT * FROM posts WHERE id = :id AND store_id = :store_id"),
        {"id": post_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise TrackingError("invalid_post", "Post is not valid for this store.")
    return row


def _variation(
    session: Session,
    tenant: TenantContext,
    campaign: Mapping[str, Any],
    adset_id: object,
    variation_id: object,
):
    variation_uuid = _uuid(variation_id, "ad_variation_id")
    adset_uuid = _uuid(adset_id, "adset_id") if adset_id is not None else None
    row = session.execute(
        text(
            """
            SELECT v.* FROM ad_variations AS v
            JOIN ad_sets AS s ON s.id = v.adset_id
            WHERE v.id = :id AND v.store_id = :store_id
              AND s.campaign_id = :campaign_id
              AND (:adset_id IS NULL OR v.adset_id = :adset_id)
            """
        ),
        {
            "id": variation_uuid,
            "store_id": tenant.store_id,
            "campaign_id": campaign["id"],
            "adset_id": adset_uuid,
        },
    ).mappings().one_or_none()
    if row is None:
        raise TrackingError(
            "invalid_ad_variation",
            "Ad variation must belong to the campaign.",
        )
    return row


def _destination(base: str, params: Mapping[str, Any]) -> str:
    query = urlencode({key: value for key, value in params.items() if value})
    return f"{base}{'&' if '?' in base else '?'}{query}"


def generate_tracking_link(
    session: Session,
    tenant: TenantContext,
    campaign_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    campaign = _campaign(session, tenant, campaign_id)

    landing_page = None
    post = None
    if payload.get("landing_page_id") is not None and payload.get("post_id") is not None:
        raise TrackingError(
            "invalid_target", "Exactly one of landing_page_id or post_id is required."
        )
    if payload.get("post_id") is not None:
        post = _post(session, tenant, payload["post_id"])
        base = post.get("published_url")
        if not base:
            raise TrackingError(
                "missing_destination", "Post has no published URL to track."
            )
    else:
        landing_page = _landing_page(
            session, tenant, campaign, payload.get("landing_page_id")
        )
        base = landing_page["published_url"] or (
            f"{PUBLIC_BASE_URL}/p/{landing_page['slug']}"
        )

    variation = None
    if payload.get("ad_variation_id") is not None:
        variation = _variation(
            session,
            tenant,
            campaign,
            payload.get("adset_id"),
            payload["ad_variation_id"],
        )

    token = f"tl_{uuid.uuid4().hex[:20]}"
    utm = {key: payload.get(key) for key in (*REQUIRED_UTM, "utm_content", "utm_term")}
    utm["utm_source"] = utm["utm_source"] or DEFAULT_UTM["utm_source"]
    utm["utm_medium"] = utm["utm_medium"] or DEFAULT_UTM["utm_medium"]
    utm["utm_campaign"] = utm["utm_campaign"] or _slug(campaign["name"])
    utm["tk"] = token
    destination_url = _destination(base, utm)

    row = session.execute(
        text(
            """
            INSERT INTO tracking_links (
                store_id, test_id, campaign_id, adset_id, ad_variation_id,
                landing_page_id, post_id, token, utm_source, utm_medium,
                utm_campaign, utm_content, utm_term, destination_url
            ) VALUES (
                :store_id, :test_id, :campaign_id, :adset_id, :ad_variation_id,
                :landing_page_id, :post_id, :token, :utm_source, :utm_medium,
                :utm_campaign, :utm_content, :utm_term, :destination_url
            )
            RETURNING *
            """
        ),
        {
            "store_id": tenant.store_id,
            "test_id": campaign["test_id"],
            "campaign_id": campaign["id"],
            "adset_id": variation["adset_id"] if variation else payload.get("adset_id"),
            "ad_variation_id": variation["id"] if variation else None,
            "landing_page_id": landing_page["id"] if landing_page else None,
            "post_id": post["id"] if post else None,
            "token": token,
            "utm_source": utm["utm_source"],
            "utm_medium": utm["utm_medium"],
            "utm_campaign": utm["utm_campaign"],
            "utm_content": utm["utm_content"],
            "utm_term": utm["utm_term"],
            "destination_url": destination_url,
        },
    ).mappings().one()

    if variation is not None:
        session.execute(
            text(
                "UPDATE ad_variations SET destination_url = :url WHERE id = :id"
            ),
            {"url": destination_url, "id": variation["id"]},
        )
    return _link_out(row)


def _link_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "test_id": str(row["test_id"]),
        "adset_id": str(row["adset_id"]) if row["adset_id"] else None,
        "ad_variation_id": (
            str(row["ad_variation_id"]) if row["ad_variation_id"] else None
        ),
        "landing_page_id": (
            str(row["landing_page_id"]) if row["landing_page_id"] else None
        ),
        "post_id": str(row["post_id"]) if row["post_id"] else None,
        "token": row["token"],
        "utm_source": row["utm_source"],
        "utm_medium": row["utm_medium"],
        "utm_campaign": row["utm_campaign"],
        "utm_content": row["utm_content"],
        "utm_term": row["utm_term"],
        "destination_url": row["destination_url"],
    }


def list_tracking_links(
    session: Session, tenant: TenantContext, campaign_id: object
) -> list[dict[str, Any]]:
    campaign = _campaign(session, tenant, campaign_id)
    rows = session.execute(
        text(
            """
            SELECT * FROM tracking_links
            WHERE campaign_id = :campaign_id AND store_id = :store_id
            ORDER BY created_at, id
            """
        ),
        {"campaign_id": campaign["id"], "store_id": tenant.store_id},
    ).mappings().all()
    return [_link_out(row) for row in rows]


def check_publication(
    session: Session,
    tenant: TenantContext,
    campaign_id: object,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    campaign = _campaign(session, tenant, campaign_id)
    payload = payload or {}
    errors: list[str] = []

    variation = None
    if payload.get("ad_variation_id") is not None:
        variation = _variation(
            session, tenant, campaign, payload.get("adset_id"), payload["ad_variation_id"]
        )
        destination = variation["destination_url"]
    else:
        rows = session.execute(
            text(
                """
                SELECT v.destination_url FROM ad_variations AS v
                JOIN ad_sets AS s ON s.id = v.adset_id
                WHERE s.campaign_id = :campaign_id AND v.store_id = :store_id
                """
            ),
            {"campaign_id": campaign["id"], "store_id": tenant.store_id},
        ).scalars().all()
        if not rows:
            errors.append("campaign has no ad variations to publish")
        destination = rows[0] if rows else None

    if not destination:
        errors.append("destination_url is missing")
        return {"valid": False, "errors": errors}

    parts = urlsplit(destination)
    query = parse_qs(parts.query)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        errors.append("destination_url is not a valid absolute URL")
    for key in REQUIRED_UTM:
        if not query.get(key):
            errors.append(f"{key} is missing from destination_url")
    token = (query.get("tk") or [None])[0]
    if token is None:
        errors.append("tracking token is missing from destination_url")
    else:
        exists = session.execute(
            text(
                "SELECT 1 FROM tracking_links "
                "WHERE token = :token AND campaign_id = :campaign_id "
                "AND store_id = :store_id "
                "AND (:variation_id IS NULL OR ad_variation_id = :variation_id)"
            ),
            {
                "token": token,
                "campaign_id": campaign["id"],
                "store_id": tenant.store_id,
                "variation_id": variation["id"] if variation else None,
            },
        ).scalar_one_or_none()
        if exists is None:
            errors.append("tracking token is not valid for this campaign")
    return {"valid": not errors, "errors": errors}


__all__ = [
    "DEFAULT_UTM",
    "REQUIRED_UTM",
    "TrackingError",
    "check_publication",
    "generate_tracking_link",
    "list_tracking_links",
]
