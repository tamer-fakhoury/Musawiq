"""Audience profile HTTP endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.services.audience import (
    AudienceNotFound,
    AudienceValidationError,
    create_profile,
    get_current,
    replace_segments,
    update_profile,
)

router = APIRouter(prefix="/audience-profiles", tags=["audience"])


class CreateProfileRequest(BaseModel):
    niche_ids: list[uuid.UUID] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    notes: str | None = None


class UpdateProfileRequest(BaseModel):
    niche_ids: list[uuid.UUID] | None = None
    languages: list[str] | None = None
    notes: str | None = None


class SegmentRequest(BaseModel):
    label: str = ""
    locations: list = Field(default_factory=list)
    age_min: int
    age_max: int
    genders: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class ReplaceSegmentsRequest(BaseModel):
    segments: list[SegmentRequest]


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _validation_error(exc: AudienceValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Audience profile not found")


@router.post("", status_code=201)
def create(
    body: CreateProfileRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return create_profile(session, tenant, body.model_dump())
    except AudienceValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/current")
def current(
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    profile = get_current(session, tenant)
    if profile is None:
        raise _not_found()
    return profile


@router.put("/{profile_id}/segments")
def replace(
    profile_id: uuid.UUID,
    body: ReplaceSegmentsRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        segments = replace_segments(
            session,
            tenant,
            profile_id,
            [segment.model_dump() for segment in body.segments],
        )
    except AudienceValidationError as exc:
        raise _validation_error(exc) from exc
    except AudienceNotFound as exc:
        raise _not_found() from exc
    return {"id": str(profile_id), "segments": segments}


@router.patch("/{profile_id}")
def patch(
    profile_id: uuid.UUID,
    body: UpdateProfileRequest,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return update_profile(
            session,
            tenant,
            profile_id,
            body.model_dump(exclude_unset=True),
        )
    except AudienceValidationError as exc:
        raise _validation_error(exc) from exc
    except AudienceNotFound as exc:
        raise _not_found() from exc


__all__ = ["router"]
