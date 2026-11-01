"""Email verification, resend limits, and login gating (FR-0.6.2)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.auth.passwords import verify_password

TOKEN_TTL_HOURS = 24
RESEND_LIMIT = 3
RESEND_WINDOW_HOURS = 1


class EmailVerificationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        *,
        retry_after: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


def _auth_lookup(session: Session) -> None:
    session.execute(
        text("SELECT set_config('app.auth_lookup', 'true', true)")
    )


def _user_id(session: Session, user_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT set_config('app.user_id', :value, true)"),
        {"value": str(user_id)},
    )


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _user_by_email(session: Session, email: str):
    _auth_lookup(session)
    return session.execute(
        text(
            "SELECT * FROM users WHERE email = :email AND deleted_at IS NULL"
        ),
        {"email": email.strip()},
    ).mappings().one_or_none()


def issue_token(
    session: Session,
    user_id: uuid.UUID,
    email: str,
    *,
    enforce_rate_limit: bool = False,
    source: str = "signup",
) -> dict[str, Any]:
    if enforce_rate_limit:
        count = session.execute(
            text(
                "SELECT count(*) FROM email_verification_tokens "
                "WHERE email = :email AND source = 'resend' "
                "AND created_at > now() - make_interval(hours => :hours)"
            ),
            {"email": email, "hours": RESEND_WINDOW_HOURS},
        ).scalar_one()
        if count >= RESEND_LIMIT:
            raise EmailVerificationError(
                "rate_limited",
                "Too many verification emails requested.",
                429,
                retry_after=3600,
            )
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    row = session.execute(
        text(
            """
            INSERT INTO email_verification_tokens (
                user_id, email, token_hash, source, expires_at
            ) VALUES (
                :user_id, :email, :token_hash, :source, :expires_at
            )
            RETURNING id, expires_at
            """
        ),
        {
            "user_id": user_id,
            "email": email,
            "token_hash": _hash(raw),
            "source": source,
            "expires_at": expires_at,
        },
    ).mappings().one()
    return {
        "token": raw,
        "id": str(row["id"]),
        "expires_at": row["expires_at"].isoformat(),
    }


def request_resend(session: Session, email: str) -> dict[str, Any]:
    if not isinstance(email, str) or not email.strip():
        raise EmailVerificationError(
            "invalid_email", "email is required.", 422
        )
    user = _user_by_email(session, email)
    if user is None or user["email_verified_at"] is not None:
        return {"sent": True, "token": None, "expires_at": None}
    issued = issue_token(
        session,
        user["id"],
        user["email"],
        enforce_rate_limit=True,
        source="resend",
    )
    return {
        "sent": True,
        "token": issued["token"],
        "expires_at": issued["expires_at"],
    }


def verify_email(session: Session, raw_token: str) -> dict[str, Any]:
    if not isinstance(raw_token, str) or not raw_token:
        raise EmailVerificationError(
            "invalid_verification_token",
            "Verification token is invalid.",
            400,
        )
    token_hash = _hash(raw_token)
    row = session.execute(
        text(
            "SELECT * FROM email_verification_tokens "
            "WHERE token_hash = :hash"
        ),
        {"hash": token_hash},
    ).mappings().one_or_none()
    if row is None:
        raise EmailVerificationError(
            "invalid_verification_token",
            "Verification token is invalid.",
            400,
        )
    if row["used_at"] is not None:
        raise EmailVerificationError(
            "invalid_verification_token",
            "Verification token was already used.",
            400,
        )
    if row["expires_at"] <= datetime.now(timezone.utc):
        raise EmailVerificationError(
            "expired_verification_token",
            "Verification token has expired.",
            400,
        )

    _user_id(session, row["user_id"])
    session.execute(
        text(
            "UPDATE users SET email_verified_at = now(), "
            "status = CASE WHEN status = 'invited' THEN 'active' ELSE status END "
            "WHERE id = :id AND deleted_at IS NULL"
        ),
        {"id": row["user_id"]},
    )
    session.execute(
        text(
            "UPDATE email_verification_tokens SET used_at = now() "
            "WHERE user_id = :user_id AND used_at IS NULL"
        ),
        {"user_id": row["user_id"]},
    )
    return {
        "verified": True,
        "user_id": str(row["user_id"]),
        "email": str(row["email"]),
    }


def login(session: Session, email: str, password: str) -> dict[str, Any]:
    if not isinstance(email, str) or not isinstance(password, str):
        raise EmailVerificationError(
            "invalid_credentials", "Invalid email or password.", 401
        )
    user = _user_by_email(session, email)
    if user is None or not verify_password(password, user["password_hash"]):
        raise EmailVerificationError(
            "invalid_credentials", "Invalid email or password.", 401
        )
    if user["email_verified_at"] is None:
        raise EmailVerificationError(
            "email_unverified",
            "Verify your email before signing in.",
            403,
        )
    _user_id(session, user["id"])
    session.execute(
        text("UPDATE users SET last_login_at = now() WHERE id = :id"),
        {"id": user["id"]},
    )
    store = session.execute(
        text(
            "SELECT id, name, slug, timezone FROM stores "
            "WHERE owner_user_id = :user_id AND deleted_at IS NULL "
            "ORDER BY created_at LIMIT 1"
        ),
        {"user_id": user["id"]},
    ).mappings().one_or_none()
    return {
        "user": {
            "id": str(user["id"]),
            "email": str(user["email"]),
            "full_name": user["full_name"],
            "role": user["role"],
            "email_verified_at": user["email_verified_at"].isoformat(),
            "password_changed_at": (
                user["password_changed_at"].isoformat()
                if user.get("password_changed_at") is not None
                else None
            ),
        },
        "active_store": (
            {
                "id": str(store["id"]),
                "name": store["name"],
                "slug": store["slug"],
                "timezone": store["timezone"],
            }
            if store is not None
            else None
        ),
    }


__all__ = [
    "EmailVerificationError",
    "RESEND_LIMIT",
    "RESEND_WINDOW_HOURS",
    "TOKEN_TTL_HOURS",
    "issue_token",
    "login",
    "request_resend",
    "verify_email",
]
