"""Campaign pre-flight validation and ad preview (FR-3.2.5)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.services.campaigns import (
    DEFAULT_MIN_BUDGET_MINOR,
    PLATFORM_MIN_BUDGET_MINOR,
)
from musawiq.services.tracking import check_publication


class PreflightError(Exception):
    """Base class for pre-flight failures."""

    def __init__(self, code: str, message: str, status_code: int = 404) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PreflightError("invalid_id", f"{name} must be a UUID.", 422) from exc


def _campaign(session: Session, tenant: TenantContext, campaign_id: object):
    campaign_uuid = _uuid(campaign_id, "campaign_id")
    row = session.execute(
        text(
            "SELECT * FROM campaigns WHERE id = :id AND store_id = :store_id"
        ),
        {"id": campaign_uuid, "store_id": tenant.store_id},
    ).mappings().one_or_none()
    if row is None:
        raise PreflightError("not_found", "Campaign not found.")
    return row


def _check_account(
    session: Session, tenant: TenantContext, campaign: Mapping[str, Any]
) -> list[dict[str, Any]]:
    row = session.execute(
        text(
            """
            SELECT status, token_expires_at,
                   (token_expires_at IS NOT NULL AND token_expires_at <= now())
                       AS expired
            FROM ad_account_connections
            WHERE store_id = :store_id AND provider = :provider
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ),
        {"store_id": tenant.store_id, "provider": campaign["provider"]},
    ).mappings().one_or_none()
    if row is None:
        return [
            {
                "code": "account_not_connected",
                "message": f"No {campaign['provider']} ad account is connected.",
            }
        ]
    issues: list[dict[str, Any]] = []
    if row["status"] != "connected":
        issues.append(
            {
                "code": "account_not_connected",
                "message": f"Ad account status is {row['status']}.",
            }
        )
    if row["expired"]:
        issues.append(
            {
                "code": "account_token_expired",
                "message": "Ad account access token has expired.",
            }
        )
    return issues


def _approved_variations(
    session: Session, tenant: TenantContext, campaign_id: uuid.UUID
) -> list[Mapping[str, Any]]:
    return session.execute(
        text(
            """
            SELECT v.* FROM ad_variations AS v
            JOIN ad_sets AS s ON s.id = v.adset_id
            WHERE s.campaign_id = :campaign_id
              AND v.store_id = :store_id
              AND v.status = 'approved'
            ORDER BY v.created_at, v.id
            """
        ),
        {"campaign_id": campaign_id, "store_id": tenant.store_id},
    ).mappings().all()


def _creative(
    session: Session, tenant: TenantContext, variation: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if variation["creative_file_id"] is not None:
        file_row = session.execute(
            text(
                "SELECT id, original_filename, mime_type, status "
                "FROM stored_files WHERE id = :id AND store_id = :store_id"
            ),
            {
                "id": variation["creative_file_id"],
                "store_id": tenant.store_id,
            },
        ).mappings().one_or_none()
        if file_row is None:
            return None, [
                {
                    "code": "creative_missing",
                    "message": "Variation creative file does not exist.",
                    "variation_id": str(variation["id"]),
                }
            ]
        return {
            "file_id": str(file_row["id"]),
            "filename": file_row["original_filename"],
            "mime_type": file_row["mime_type"],
        }, []
    if variation["primary_creative_id"] is not None:
        creative_row = session.execute(
            text(
                "SELECT id, approval_state, type FROM creatives "
                "WHERE id = :id AND store_id = :store_id"
            ),
            {
                "id": variation["primary_creative_id"],
                "store_id": tenant.store_id,
            },
        ).mappings().one_or_none()
        if creative_row is None:
            return None, [
                {
                    "code": "creative_missing",
                    "message": "Variation creative does not exist.",
                    "variation_id": str(variation["id"]),
                }
            ]
        if creative_row["approval_state"] != "approved":
            return None, [
                {
                    "code": "creative_not_approved",
                    "message": "Variation creative is not approved.",
                    "variation_id": str(variation["id"]),
                }
            ]
        return {
            "creative_id": str(creative_row["id"]),
            "type": creative_row["type"],
            "approval_state": creative_row["approval_state"],
        }, []
    return None, [
        {
            "code": "creative_missing",
            "message": "Approved variation has no creative.",
            "variation_id": str(variation["id"]),
        }
    ]


def validate(
    session: Session, tenant: TenantContext, campaign_id: object
) -> dict[str, Any]:
    campaign = _campaign(session, tenant, campaign_id)
    unresolved: list[dict[str, Any]] = []
    unresolved.extend(_check_account(session, tenant, campaign))

    minimum = PLATFORM_MIN_BUDGET_MINOR.get(
        campaign["provider"], DEFAULT_MIN_BUDGET_MINOR
    )
    if campaign["budget_minor"] < minimum:
        unresolved.append(
            {
                "code": "budget_below_minimum",
                "message": f"Budget must be at least {minimum} minor units for "
                f"{campaign['provider']}.",
            }
        )

    pages = session.execute(
        text(
            "SELECT id, status, published_url FROM landing_pages "
            "WHERE test_id = :test_id AND store_id = :store_id "
            "AND deleted_at IS NULL"
        ),
        {"test_id": campaign["test_id"], "store_id": tenant.store_id},
    ).mappings().all()
    published = [page for page in pages if page["status"] == "published"]
    if not published:
        unresolved.append(
            {
                "code": "landing_page_not_published",
                "message": "Campaign needs a published landing page.",
            }
        )

    variations = _approved_variations(session, tenant, campaign["id"])
    if not variations:
        unresolved.append(
            {
                "code": "no_approved_variation",
                "message": "At least one ad variation must be approved.",
            }
        )

    preview: list[dict[str, Any]] = []
    for variation in variations:
        creative, issues = _creative(session, tenant, variation)
        unresolved.extend(issues)
        tracking = check_publication(
            session, tenant, campaign["id"], {"ad_variation_id": variation["id"]}
        )
        for message in tracking["errors"]:
            unresolved.append(
                {
                    "code": "tracking_invalid",
                    "message": message,
                    "variation_id": str(variation["id"]),
                }
            )
        preview.append(
            {
                "variation_id": str(variation["id"]),
                "name": variation["name"],
                "headline": variation["headline"],
                "copy_text": variation["copy_text"],
                "description": variation["description"],
                "destination_url": variation["destination_url"],
                "creative": creative,
            }
        )

    return {
        "valid": not unresolved,
        "unresolved": unresolved,
        "preview": {
            "campaign_id": str(campaign["id"]),
            "landing_page_id": (
                str(published[0]["id"]) if published else None
            ),
            "variations": preview,
        },
    }


__all__ = ["PreflightError", "validate"]
