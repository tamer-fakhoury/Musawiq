"""Password reset tokens and reset flow (FR-0.6.5)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.auth.signup import MIN_PASSWORD_LENGTH, hash_password

TOKEN_TTL_HOURS = 1
TOKEN_PURPOSE = "password_reset"


class PasswordResetError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _auth_lookup(session: Session) -> None:
    session.execute(
        text("SELECT set_config('app.auth_lookup', 'true', true)")
    )


def forgot_password(session: Session, email: object) -> dict[str, Any]:
    """Always succeeds; issues a token only when the account exists."""
    result: dict[str, Any] = {"status": "accepted"}
    if not isinstance(email, str) or not email.strip():
        return result
    _auth_lookup(session)
    user = session.execute(
        text(
            "SELECT id, email FROM users WHERE email = :email "
            "AND status = 'active' AND deleted_at IS NULL"
        ),
        {"email": email.strip().lower()},
    ).mappings().one_or_none()
    if user is None:
        return result

    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    session.execute(
        text(
            """
            INSERT INTO email_verification_tokens (
                user_id, email, token_hash, source, purpose, expires_at
            ) VALUES (
                :user_id, :email, :token_hash, 'password_reset',
                :purpose, :expires_at
            )
            """
        ),
        {
            "user_id": user["id"],
            "email": str(user["email"]),
            "token_hash": _hash(raw),
            "purpose": TOKEN_PURPOSE,
            "expires_at": expires_at,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO async_jobs (
                store_id, job_type, state, payload, attempt_count, max_attempts
            ) VALUES (
                NULL, 'email_verification', 'queued', :payload, 0, 3
            )
            """
        ),
        {
            "payload": Jsonb(
                {
                    "schema_version": 1,
                    "purpose": TOKEN_PURPOSE,
                    "user_id": str(user["id"]),
                    "email": str(user["email"]),
                    "token": raw,
                }
            )
        },
    )
    result["token"] = raw
    result["expires_at"] = expires_at.isoformat()
    return result


def reset_password(session: Session, payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("token")
    password = payload.get("password")
    if not isinstance(raw, str) or not raw.strip():
        raise PasswordResetError("invalid_token", "This reset link is invalid.")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordResetError(
            "weak_password",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    row = session.execute(
        text(
            """
            SELECT id, user_id FROM email_verification_tokens
            WHERE token_hash = :token_hash AND purpose = :purpose
              AND used_at IS NULL AND expires_at > now()
            FOR UPDATE
            """
        ),
        {"token_hash": _hash(raw.strip()), "purpose": TOKEN_PURPOSE},
    ).mappings().one_or_none()
    if row is None:
        raise PasswordResetError("invalid_token", "This reset link is invalid.")

    session.execute(
        text(
            "UPDATE email_verification_tokens SET used_at = now() "
            "WHERE user_id = :user_id AND purpose = :purpose AND used_at IS NULL"
        ),
        {"user_id": row["user_id"], "purpose": TOKEN_PURPOSE},
    )
    updated = session.execute(
        text(
            "UPDATE users SET password_hash = :password_hash, "
            "password_changed_at = now(), updated_at = now() "
            "WHERE id = :id RETURNING id"
        ),
        {
            "id": row["user_id"],
            "password_hash": hash_password(password),
        },
    ).scalar_one_or_none()
    if updated is None:
        raise PasswordResetError("invalid_token", "This reset link is invalid.")
    return {"status": "password_reset", "user_id": str(updated)}


__all__ = [
    "PasswordResetError",
    "TOKEN_PURPOSE",
    "TOKEN_TTL_HOURS",
    "forgot_password",
    "reset_password",
]
