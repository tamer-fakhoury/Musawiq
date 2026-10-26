"""Taxonomy read endpoints for categories and niches."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext

router = APIRouter(tags=["taxonomy"])


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


@router.get("/categories")
def list_categories(
    session: Session = Depends(get_session),
    _: None = Depends(_require_action(Action.READ)),
):
    rows = session.execute(
        text(
            """
            SELECT id, parent_id, name, slug, sort_order
            FROM categories
            WHERE is_active
            ORDER BY sort_order, name
            """
        )
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "parent_id": (
                str(row["parent_id"]) if row["parent_id"] is not None else None
            ),
            "name": row["name"],
            "slug": row["slug"],
            "sort_order": row["sort_order"],
        }
        for row in rows
    ]


@router.get("/niches")
def list_niches(
    category_id: uuid.UUID = Query(...),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    rows = session.execute(
        text(
            """
            SELECT id, category_id, store_id, name, slug
            FROM niches
            WHERE category_id = :category_id
              AND (store_id IS NULL OR store_id = :store_id)
            ORDER BY name, id
            """
        ),
        {"category_id": category_id, "store_id": tenant.store_id},
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "category_id": str(row["category_id"]),
            "store_id": str(row["store_id"]) if row["store_id"] else None,
            "name": row["name"],
            "slug": row["slug"],
        }
        for row in rows
    ]


__all__ = ["router"]
