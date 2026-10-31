"""Campaign publication via an ad platform client (FR-3.2.7)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.preflight import validate as preflight

ACTIONABLE_ERRORS = {
    "rate_limited": "The ad platform is rate limiting requests. Wait a moment and retry.",
    "auth_expired": "The ad account connection expired. Reconnect the account and retry.",
    "invalid_budget": "The platform rejected the budget. Adjust it to the allowed range.",
    "invalid_creative": "A creative was rejected by the platform. Replace it and retry.",
    "policy_rejection": "The platform rejected the campaign policy. Review the copy and targeting.",
    "network_error": "The ad platform could not be reached. Retry the submission.",
}
DEFAULT_ERROR_MESSAGE = (
    "The ad platform rejected the submission. Review the campaign and retry."
)
SENSITIVE_KEYS = ("token", "secret", "authorization", "password", "api_key")
ACTIVE_EXTERNAL_STATES = frozenset({"submitted", "active"})


class PublicationError(Exception):
    """Base class for campaign publication failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PlatformError(Exception):
    """Raised by an ad platform client for a rejected submission."""

    def __init__(self, code: str, raw: Any = None) -> None:
        self.code = code
        self.raw = raw
        super().__init__(code)

    @property
    def merchant_message(self) -> str:
        return ACTIONABLE_ERRORS.get(self.code, DEFAULT_ERROR_MESSAGE)


@dataclass(frozen=True)
class PublishResult:
    external_id: str
    status: str = "submitted"
    raw_response: Any = None


class AdPlatformClient(Protocol):
    def publish_campaign(self, request: Mapping[str, Any]) -> PublishResult:
        ...


@dataclass
class FixtureAdPlatformClient:
    """Deterministic offline platform client used when no real client is wired."""

    provider: str = "meta"

    def publish_campaign(self, request: Mapping[str, Any]) -> PublishResult:
        campaign_id = request.get("campaign_id", "unknown")
        return PublishResult(
            external_id=f"fx_{self.provider}_{campaign_id}",
            status="submitted",
            raw_response={"accepted": True},
        )


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                "[redacted]"
                if any(marker in str(key).lower() for marker in SENSITIVE_KEYS)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _campaign(session: Session, tenant: TenantContext, campaign_id: object):
    try:
        campaign_uuid = uuid.UUID(str(campaign_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PublicationError(
            "invalid_campaign_id", "campaign_id must be a UUID."
        ) from exc
    row = session.execute(
        text(
            "SELECT * FROM campaigns WHERE id = :id AND store_id = :store_id"
        ),
        {"id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise PublicationError("not_found", "Campaign not found.", 404)
    return row


def _attempt_for(
    session: Session, tenant: TenantContext, campaign_id: uuid.UUID
):
    return session.execute(
        text(
            """
            SELECT * FROM publication_attempts
            WHERE campaign_id = :campaign_id AND store_id = :store_id
            ORDER BY created_at, id
            LIMIT 1
            """
        ),
        {"campaign_id": campaign_id, "store_id": tenant.store_id},
    ).mappings().one_or_none()


def _attempt_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "provider": row["provider"],
        "attempt_number": row["attempt_number"],
        "status": row["status"],
        "external_id": row["external_id"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "submitted_by": str(row["submitted_by"]),
        "submitted_at": (
            row["submitted_at"].isoformat() if row["submitted_at"] else None
        ),
    }


def _approved_by(
    session: Session, tenant: TenantContext, approved_by: object
) -> uuid.UUID:
    user_id = uuid.UUID(str(approved_by)) if approved_by else tenant.user_id
    row = session.execute(
        text("SELECT role, status FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().one_or_none()
    if row is None or row["status"] != "active":
        raise PublicationError(
            "invalid_approver", "Approver must be an active user."
        )
    if row["role"] not in {"owner", "manager"}:
        raise PublicationError(
            "approval_forbidden",
            "Only an owner or manager can approve publication.",
            403,
        )
    return user_id


def _request_payload(
    session: Session, tenant: TenantContext, campaign: Mapping[str, Any]
) -> dict[str, Any]:
    adsets = session.execute(
        text(
            "SELECT id, name, targeting, budget_type, budget_minor, currency, "
            "start_at, end_at FROM ad_sets "
            "WHERE campaign_id = :id AND store_id = :store_id ORDER BY created_at"
        ),
        {"id": campaign["id"], "store_id": tenant.store_id},
    ).mappings().all()
    variations = session.execute(
        text(
            """
            SELECT v.id, v.adset_id, v.headline, v.copy_text, v.description,
                   v.destination_url, v.creative_file_id
            FROM ad_variations AS v
            JOIN ad_sets AS s ON s.id = v.adset_id
            WHERE s.campaign_id = :id AND v.store_id = :store_id
              AND v.status = 'approved'
            ORDER BY v.created_at, v.id
            """
        ),
        {"id": campaign["id"], "store_id": tenant.store_id},
    ).mappings().all()
    return {
        "campaign_id": str(campaign["id"]),
        "provider": campaign["provider"],
        "name": campaign["name"],
        "objective": campaign["objective"],
        "budget_type": campaign["budget_type"],
        "budget_minor": campaign["budget_minor"],
        "currency": campaign["currency"].strip(),
        "start_at": campaign["start_at"].isoformat(),
        "end_at": campaign["end_at"].isoformat(),
        "ad_sets": [
            {
                "id": str(adset["id"]),
                "name": adset["name"],
                "targeting": adset["targeting"],
                "budget_type": adset["budget_type"],
                "budget_minor": adset["budget_minor"],
                "currency": adset["currency"].strip() if adset["currency"] else None,
                "start_at": adset["start_at"].isoformat() if adset["start_at"] else None,
                "end_at": adset["end_at"].isoformat() if adset["end_at"] else None,
            }
            for adset in adsets
        ],
        "variations": [
            {
                "id": str(variation["id"]),
                "adset_id": str(variation["adset_id"]),
                "headline": variation["headline"],
                "copy_text": variation["copy_text"],
                "description": variation["description"],
                "destination_url": variation["destination_url"],
                "creative_file_id": (
                    str(variation["creative_file_id"])
                    if variation["creative_file_id"]
                    else None
                ),
            }
            for variation in variations
        ],
        "access_token": "[redacted]",
    }


def publish_campaign(
    session: Session,
    tenant: TenantContext,
    campaign_id: object,
    *,
    confirm: bool = False,
    approved_by: object = None,
    client: AdPlatformClient | None = None,
) -> dict[str, Any]:
    if not confirm:
        raise PublicationError(
            "approval_required", "Explicit merchant approval is required."
        )
    approver = _approved_by(session, tenant, approved_by)
    campaign = _campaign(session, tenant, campaign_id)

    existing_attempt = _attempt_for(session, tenant, campaign["id"])
    if (
        campaign["external_campaign_id"]
        and campaign["status"] in ACTIVE_EXTERNAL_STATES
        and existing_attempt is not None
    ):
        return {
            "attempt": _attempt_out(existing_attempt),
            "campaign_status": campaign["status"],
            "external_campaign_id": campaign["external_campaign_id"],
        }

    result = preflight(session, tenant, campaign["id"])
    if not result["valid"]:
        codes = ", ".join(
            item["code"] for item in result["unresolved"]
        )
        raise PublicationError(
            "campaign_invalid",
            f"Resolve the pre-flight items before publishing: {codes}.",
        )

    payload = redact(_request_payload(session, tenant, campaign))
    if client is None:
        raise PublicationError(
            "platform_not_configured",
            "No live ad platform client is configured.",
            503,
        )

    attempt_number = (
        existing_attempt["attempt_number"] if existing_attempt else 1
    )
    if existing_attempt is None:
        attempt_id = session.execute(
            text(
                """
                INSERT INTO publication_attempts (
                    store_id, campaign_id, provider, attempt_number, status,
                    request_payload, submitted_by, submitted_at
                ) VALUES (
                    :store_id, :campaign_id, :provider, :attempt_number,
                    'pending', :request_payload, :submitted_by, now()
                )
                RETURNING id
                """
            ),
            {
                "store_id": tenant.store_id,
                "campaign_id": campaign["id"],
                "provider": campaign["provider"],
                "attempt_number": attempt_number,
                "request_payload": Jsonb(payload),
                "submitted_by": approver,
            },
        ).scalar_one()
    else:
        attempt_id = existing_attempt["id"]
        session.execute(
            text(
                """
                UPDATE publication_attempts
                SET status = 'pending', request_payload = :request_payload,
                    submitted_by = :submitted_by, submitted_at = now(),
                    error_code = NULL, error_message = NULL,
                    external_id = NULL, response_payload = NULL
                WHERE id = :id AND store_id = :store_id
                """
            ),
            {
                "id": attempt_id,
                "store_id": tenant.store_id,
                "request_payload": Jsonb(payload),
                "submitted_by": approver,
            },
        )

    try:
        result_value = client.publish_campaign(payload)
    except PlatformError as exc:
        session.execute(
            text(
                """
                UPDATE publication_attempts
                SET status = 'failed', error_code = :error_code,
                    error_message = :error_message,
                    response_payload = :response_payload
                WHERE id = :id AND store_id = :store_id
                """
            ),
            {
                "id": attempt_id,
                "store_id": tenant.store_id,
                "error_code": exc.code,
                "error_message": exc.merchant_message,
                "response_payload": Jsonb(redact(exc.raw or {})),
            },
        )
        session.execute(
            text(
                "UPDATE campaigns SET status = 'failed' "
                "WHERE id = :id AND store_id = :store_id"
            ),
            {"id": campaign["id"], "store_id": tenant.store_id},
        )
        attempt = session.execute(
            text("SELECT * FROM publication_attempts WHERE id = :id"),
            {"id": attempt_id},
        ).mappings().one()
        return {
            "attempt": _attempt_out(attempt),
            "campaign_status": "failed",
            "external_campaign_id": None,
        }

    campaign_status = (
        result_value.status
        if result_value.status in {"submitted", "active"}
        else "submitted"
    )
    session.execute(
        text(
            """
            UPDATE publication_attempts
            SET status = 'succeeded', external_id = :external_id,
                response_payload = :response_payload
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {
            "id": attempt_id,
            "store_id": tenant.store_id,
            "external_id": result_value.external_id,
            "response_payload": Jsonb(redact(result_value.raw_response or {})),
        },
    )
    session.execute(
        text(
            """
            UPDATE campaigns
            SET status = :status, external_campaign_id = :external_id
            WHERE id = :id AND store_id = :store_id
            """
        ),
        {
            "id": campaign["id"],
            "store_id": tenant.store_id,
            "status": campaign_status,
            "external_id": result_value.external_id,
        },
    )
    attempt = session.execute(
        text("SELECT * FROM publication_attempts WHERE id = :id"),
        {"id": attempt_id},
    ).mappings().one()
    return {
        "attempt": _attempt_out(attempt),
        "campaign_status": campaign_status,
        "external_campaign_id": result_value.external_id,
    }


__all__ = [
    "ACTIONABLE_ERRORS",
    "AdPlatformClient",
    "PlatformError",
    "PublicationError",
    "PublishResult",
    "publish_campaign",
    "redact",
]
