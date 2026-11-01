"""Public authentication endpoints (FR-0.6.1)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from musawiq.auth.signup import SignupError, signup
from musawiq.config import get_settings
from musawiq.db.session import get_session_factory
from musawiq.middleware.errors import error_response
from musawiq.services.email_verification import (
    EmailVerificationError,
    login,
    request_resend,
    verify_email,
)

router = APIRouter(tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/signup", status_code=201)
def create_account(payload: SignupRequest, request: Request):
    session = get_session_factory()()
    try:
        session.begin()
        result = signup(session, payload.model_dump())
        session.commit()
    except SignupError as exc:
        session.rollback()
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    finally:
        session.close()
    return result


class ResendRequest(BaseModel):
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


def _verification_error(request: Request, exc: EmailVerificationError):
    headers = (
        {"Retry-After": str(exc.retry_after)}
        if exc.retry_after is not None
        else None
    )
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        headers=headers,
    )


@router.get("/auth/verify")
def verify(token: str, request: Request):
    session = get_session_factory()()
    try:
        session.begin()
        result = verify_email(session, token)
        session.commit()
    except EmailVerificationError as exc:
        session.rollback()
        return _verification_error(request, exc)
    finally:
        session.close()
    return result


@router.post("/auth/verify/resend", status_code=202)
def resend_verification(payload: ResendRequest, request: Request):
    session = get_session_factory()()
    try:
        session.begin()
        result = request_resend(session, payload.email)
        session.commit()
    except EmailVerificationError as exc:
        session.rollback()
        return _verification_error(request, exc)
    finally:
        session.close()
    settings = get_settings()
    if settings.app_env == "development" and result.get("token"):
        return {
            "sent": True,
            "verification_token": result["token"],
            "expires_at": result["expires_at"],
        }
    return {"sent": True, "expires_at": result.get("expires_at")}


@router.post("/auth/login")
def login_user(payload: LoginRequest, request: Request):
    session = get_session_factory()()
    try:
        session.begin()
        result = login(session, payload.email, payload.password)
        session.commit()
    except EmailVerificationError as exc:
        session.rollback()
        return _verification_error(request, exc)
    finally:
        session.close()
    return result


__all__ = ["router"]
