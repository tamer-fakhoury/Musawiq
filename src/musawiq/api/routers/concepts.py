"""Product concept draft HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from musawiq.api.deps import get_session, get_tenant
from musawiq.auth.permissions import Action
from musawiq.auth.service import AuthorizationService
from musawiq.db.tenant import TenantContext
from musawiq.middleware.errors import error_response
from musawiq.services.concepts import (
    CONCEPT_FIELDS,
    ConceptConflict,
    ConceptNotFound,
    ConceptValidationError,
    UploadedImage,
    archive_concept,
    create_concept,
    delete_concept,
    get_concept,
    list_concepts,
    unarchive_concept,
    update_concept,
    upload_product_image,
)
from musawiq.services.sufficiency import (
    get_latest_sufficiency_check,
    run_sufficiency_check,
)

router = APIRouter(prefix="/product-concepts", tags=["concepts"])


def _require_action(action: Action):
    def dependency(request: Request) -> None:
        tenant = getattr(request.state, "tenant", None)
        role = getattr(tenant, "role", None) or getattr(
            request.state, "role", None
        )
        AuthorizationService().check(role, action)

    return dependency


def _validation_response(request: Request, exc: ConceptValidationError):
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        fields=exc.fields,
    )


def _not_found_response(request: Request):
    return error_response(
        request,
        status_code=404,
        code="not_found",
        message="Product concept not found.",
    )


def _conflict_response(request: Request, exc: ConceptConflict):
    return error_response(
        request,
        status_code=409,
        code="conflict",
        message=str(exc),
    )


async def _read_payload(
    request: Request,
) -> tuple[dict[str, Any], UploadedImage | None]:
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )

    if content_type == "application/json":
        try:
            body = await request.json()
        except (TypeError, ValueError) as exc:
            raise ConceptValidationError(
                {"body": "body must be valid JSON"}
            ) from exc
        if not isinstance(body, dict):
            raise ConceptValidationError(
                {"body": "body must be a JSON object"}
            )
        return body, None

    if content_type in {
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    }:
        form = await request.form()
        payload = {
            field: form.get(field)
            for field in CONCEPT_FIELDS
            if field in form
        }
        if "version" in form:
            payload["version"] = form.get("version")
        upload = form.get("image") or form.get("file")
        image = None
        if upload is not None and hasattr(upload, "read"):
            image = UploadedImage(
                filename=getattr(upload, "filename", "") or "",
                content_type=getattr(upload, "content_type", "") or "",
                data=await upload.read(),
            )
        return payload, image

    raise ConceptValidationError(
        {
            "body": (
                "content type must be application/json or multipart/form-data"
            )
        }
    )


def _version_value(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConceptValidationError(
            {"version": "version must be a positive integer"}
        )
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise ConceptValidationError(
            {"version": "version must be a positive integer"}
        ) from exc
    if version < 1:
        raise ConceptValidationError(
            {"version": "version must be a positive integer"}
        )
    return version


def _header_version(request: Request) -> int | None:
    raw = request.headers.get("if-match")
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if value.startswith("W/"):
        value = value[2:].strip()
    return _version_value(value.strip('"'))


def _expected_version(
    request: Request, payload: dict[str, Any]
) -> int | None:
    header = _header_version(request)
    body = _version_value(payload.get("version"))
    if header is not None and body is not None and header != body:
        raise ConceptValidationError(
            {"version": "If-Match and body version must match"}
        )
    return header if header is not None else body


@router.get("")
def list_all(
    request: Request,
    status: str | None = None,
    category_id: uuid.UUID | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    q: str | None = None,
    sort: str = "created_at",
    sort_by: str | None = None,
    direction: str = "desc",
    order: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return list_concepts(
            session,
            tenant,
            status=status,
            category_id=category_id,
            created_from=created_from or date_from,
            created_to=created_to or date_to,
            search=search or q,
            sort=sort_by or sort,
            direction=order or direction,
            limit=limit,
            offset=offset,
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)


@router.post("", status_code=201)
async def create(
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        payload, image = await _read_payload(request)
        return create_concept(session, tenant, payload, image=image)
    except ConceptValidationError as exc:
        return _validation_response(request, exc)


@router.post("/images", status_code=201)
def upload_image(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        return upload_product_image(
            session,
            tenant,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=file.file.read(),
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)


@router.get("/{concept_id}")
def detail(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        return get_concept(session, tenant, concept_id)
    except ConceptNotFound:
        return _not_found_response(request)


@router.patch("/{concept_id}")
async def patch(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        payload, image = await _read_payload(request)
        expected_version = _expected_version(request, payload)
        status = payload.get("status")
        has_fields = any(field in payload for field in CONCEPT_FIELDS)
        if status is not None and not has_fields and image is None:
            if status == "archived":
                return archive_concept(
                    session,
                    tenant,
                    concept_id,
                    expected_version=expected_version,
                )
            if status == "draft":
                return unarchive_concept(
                    session,
                    tenant,
                    concept_id,
                    expected_version=expected_version,
                )
            raise ConceptValidationError(
                {"status": "status must be archived or draft"}
            )
        return update_concept(
            session,
            tenant,
            concept_id,
            payload,
            image=image,
            expected_version=expected_version,
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)
    except ConceptNotFound:
        return _not_found_response(request)
    except ConceptConflict as exc:
        return _conflict_response(request, exc)


@router.post("/{concept_id}/archive")
def archive(
    concept_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] | None = None,
    version: int | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        payload: dict[str, Any] = dict(body or {})
        if version is not None:
            payload["version"] = version
        return archive_concept(
            session,
            tenant,
            concept_id,
            expected_version=_expected_version(request, payload),
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)
    except ConceptNotFound:
        return _not_found_response(request)
    except ConceptConflict as exc:
        return _conflict_response(request, exc)


@router.post("/{concept_id}/unarchive")
def unarchive(
    concept_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] | None = None,
    version: int | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        payload: dict[str, Any] = dict(body or {})
        if version is not None:
            payload["version"] = version
        return unarchive_concept(
            session,
            tenant,
            concept_id,
            expected_version=_expected_version(request, payload),
        )
    except ConceptValidationError as exc:
        return _validation_response(request, exc)
    except ConceptNotFound:
        return _not_found_response(request)
    except ConceptConflict as exc:
        return _conflict_response(request, exc)


@router.delete("/{concept_id}", status_code=204)
def delete(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.WRITE)),
):
    try:
        delete_concept(session, tenant, concept_id)
    except ConceptNotFound:
        return _not_found_response(request)
    except ConceptConflict as exc:
        return _conflict_response(request, exc)
    return Response(status_code=204)


@router.post("/{concept_id}/sufficiency-checks", status_code=201)
@router.post(
    "/{concept_id}/sufficiency-check",
    status_code=201,
    include_in_schema=False,
)
def run_sufficiency(
    concept_id: uuid.UUID,
    request: Request,
    body: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    competitive_data = None
    if body is not None:
        competitive_data = body.get("competitive_data")
        if competitive_data is not None and not isinstance(
            competitive_data, dict
        ):
            return _validation_response(
                request,
                ConceptValidationError(
                    {
                        "competitive_data": (
                            "competitive_data must be an object"
                        )
                    }
                ),
            )
    try:
        return run_sufficiency_check(
            session,
            tenant,
            concept_id,
            competitive_data=competitive_data,
        )
    except ConceptNotFound:
        return _not_found_response(request)


@router.get("/{concept_id}/sufficiency-checks/latest")
@router.get(
    "/{concept_id}/sufficiency-check/latest",
    include_in_schema=False,
)
def latest_sufficiency(
    concept_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    tenant: TenantContext = Depends(get_tenant),
    _: None = Depends(_require_action(Action.READ)),
):
    try:
        result = get_latest_sufficiency_check(
            session, tenant, concept_id
        )
    except ConceptNotFound:
        return _not_found_response(request)
    if result is None:
        return _not_found_response(request)
    return result


__all__ = ["router"]
