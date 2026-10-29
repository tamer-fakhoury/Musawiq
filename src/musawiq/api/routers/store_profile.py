"""Store profile endpoints: selected categories and niches."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.store_profile import (
    StoreProfileError,
    get_store_profile,
    update_store_profile,
)

router = APIRouter(prefix="/store", tags=["store"])


class UpdateProfileRequest(BaseModel):
    category_ids: list[str]
    niche_ids: list[str] = []


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


@router.get("/profile")
def read_profile(
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    return get_store_profile(session, tenant)


@router.put("/profile")
def save_profile(
    payload: UpdateProfileRequest,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return update_store_profile(
            session,
            tenant,
            category_ids=payload.category_ids,
            niche_ids=payload.niche_ids,
        )
    except StoreProfileError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )


__all__ = ["router"]
