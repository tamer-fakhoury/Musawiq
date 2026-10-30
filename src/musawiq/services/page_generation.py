"""Landing page generation job: render the responsive template as a new version."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text

from musawiq.db.session import get_session_factory
from musawiq.db.tenant import set_local_tenant
from musawiq.jobs.models import JobOutcome
from musawiq.jobs.queue import enqueue
from musawiq.services.landing_pages import (
    PAGE_TEMPLATE_SCHEMA,
    LandingPageError,
)

PAGE_MODEL_VERSION = "template-responsive-v1"


def request_generation(session, tenant, page_id) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """
            SELECT status FROM landing_pages
            WHERE id = :id AND store_id = :store_id AND deleted_at IS NULL
            """
        ),
        {"id": page_id, "store_id": tenant.store_id},
    ).one_or_none()
    if row is None:
        raise LandingPageError("not_found", "Landing page not found.", status_code=404)
    if row[0] != "draft":
        raise LandingPageError(
            "not_draft", "Only draft landing pages can be generated.", status_code=409
        )
    return enqueue(
        "page_generation",
        {
            "landing_page_id": str(page_id),
            "requested_by": str(tenant.user_id),
            "requested_role": tenant.role,
        },
        session=session,
    )


def _render(page: Mapping[str, Any], version: Mapping[str, Any], template) -> dict[str, Any]:
    body = version["content"] or {}
    schema = template["schema"] or PAGE_TEMPLATE_SCHEMA
    return {
        "schema_version": 1,
        "template": {"key": template["key"], "version": template["version"]},
        "language": page["language"],
        "sections": schema.get("sections", PAGE_TEMPLATE_SCHEMA["sections"]),
        "breakpoints": schema.get(
            "breakpoints", PAGE_TEMPLATE_SCHEMA["breakpoints"]
        ),
        "product": {
            "name": body.get("name"),
            "description": body.get("description"),
            "price_minor": version["price_minor"],
            "currency": version["currency"].strip(),
            "image_file_ids": [str(item) for item in version["image_file_ids"]],
            "target_market": body.get("target_market"),
        },
        "order_method": {
            "type": version["channel_type"],
            "whatsapp_number": version["whatsapp_number"],
            "whatsapp_message_template": version["whatsapp_message_template"],
            "cod_form_schema": version["cod_form_schema"],
        },
    }


def run_page_generation_job(job: Mapping[str, Any]) -> JobOutcome:
    payload = job.get("payload") or {}
    raw_page_id = payload.get("landing_page_id")
    if not raw_page_id:
        return JobOutcome(
            state="failed",
            error_code="invalid_payload",
            error_message="landing_page_id is required",
        )

    session = get_session_factory()()
    try:
        session.begin()
        store_id = job["store_id"]
        requested_by = payload.get("requested_by")
        if not requested_by:
            requested_by = session.execute(
                text("SELECT owner_user_id FROM stores WHERE id = :id"),
                {"id": store_id},
            ).scalar_one()
        tenant = set_local_tenant(
            session, store_id, requested_by, str(payload.get("requested_role") or "owner")
        )
        page = session.execute(
            text(
                """
                SELECT * FROM landing_pages
                WHERE id = :id AND store_id = :store_id AND deleted_at IS NULL
                """
            ),
            {"id": raw_page_id, "store_id": store_id},
        ).mappings().one_or_none()
        if page is None:
            return JobOutcome(
                state="failed",
                error_code="landing_page_not_found",
                error_message="Landing page does not exist for this store",
            )
        if page["status"] != "draft":
            return JobOutcome(
                state="failed",
                error_code="not_draft",
                error_message="Only draft landing pages can be generated",
            )
        if page["current_version_id"] is None:
            return JobOutcome(
                state="failed",
                error_code="incomplete_input",
                error_message="Landing page has no draft input to generate from",
            )

        version = session.execute(
            text(
                """
                SELECT pv.*, oc.type AS channel_type,
                       oc.whatsapp_number AS whatsapp_number,
                       oc.whatsapp_message_template AS whatsapp_message_template,
                       oc.cod_form_schema AS cod_form_schema
                FROM page_versions AS pv
                LEFT JOIN order_channels AS oc
                    ON oc.id = pv.order_channel_id
                WHERE pv.id = :id
                """
            ),
            {"id": page["current_version_id"]},
        ).mappings().one()
        body = version["content"] or {}
        if (
            not body.get("name")
            or not version["price_minor"]
            or version["price_minor"] <= 0
            or version["channel_type"] is None
        ):
            return JobOutcome(
                state="failed",
                error_code="incomplete_input",
                error_message="Product name, price, and order method are required",
            )

        template = session.execute(
            text("SELECT * FROM page_templates WHERE id = :id"),
            {"id": page["template_id"]},
        ).mappings().one()

        next_version = session.execute(
            text(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM page_versions "
                "WHERE landing_page_id = :id"
            ),
            {"id": page["id"]},
        ).scalar_one()
        rendered = _render(page, version, template)
        new_version_id = session.execute(
            text(
                """
                INSERT INTO page_versions (
                    store_id, landing_page_id, version, content, price_minor,
                    currency, image_file_ids, order_channel_id, generated_by,
                    model_version, created_by
                ) VALUES (
                    :store_id, :landing_page_id, :version, :content,
                    :price_minor, :currency, CAST(:image_ids AS uuid[]),
                    :order_channel_id, 'ai', :model_version, :created_by
                )
                RETURNING id
                """
            ),
            {
                "store_id": store_id,
                "landing_page_id": page["id"],
                "version": next_version,
                "content": Jsonb(rendered),
                "price_minor": version["price_minor"],
                "currency": version["currency"],
                "image_ids": version["image_file_ids"],
                "order_channel_id": version["order_channel_id"],
                "model_version": PAGE_MODEL_VERSION,
                "created_by": requested_by or version["created_by"],
            },
        ).scalar_one()
        session.execute(
            text(
                "UPDATE landing_pages SET current_version_id = :id "
                "WHERE id = :page"
            ),
            {"id": new_version_id, "page": page["id"]},
        )
        if page["status"] == "published":
            session.execute(
                text(
                    "UPDATE landing_pages SET published_version_id = :id, "
                    "published_at = now() WHERE id = :page"
                ),
                {"id": new_version_id, "page": page["id"]},
            )
        session.commit()
        return JobOutcome(
            state="succeeded",
            result={
                "landing_page_id": str(page["id"]),
                "version": next_version,
                "generated_by": "ai",
                "model_version": PAGE_MODEL_VERSION,
            },
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "PAGE_MODEL_VERSION",
    "request_generation",
    "run_page_generation_job",
]
