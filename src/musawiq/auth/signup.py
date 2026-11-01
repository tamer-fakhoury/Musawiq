"""Account signup with argon2id password hashing (FR-0.6.1)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from argon2 import PasswordHasher
from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.services.email_verification import issue_token

MIN_PASSWORD_LENGTH = 12
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_hasher = PasswordHasher()  # argon2id is the default type


class SignupError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _validated(payload: Mapping[str, Any]) -> tuple[str, str]:
    email = payload.get("email")
    if not isinstance(email, str) or not EMAIL_PATTERN.fullmatch(email.strip()):
        raise SignupError("invalid_email", "Enter a valid email address.")
    password = payload.get("password")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise SignupError(
            "weak_password",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )
    return email.strip().lower(), password


def signup(session: Session, payload: Mapping[str, Any]) -> dict[str, Any]:
    email, password = _validated(payload)
    password_hash = hash_password(password)
    user_id = uuid.uuid4()

    session.execute(
        text("SELECT set_config('app.user_id', :value, true)"),
        {"value": str(user_id)},
    )
    inserted = session.execute(
        text(
            """
            INSERT INTO users (
                id, email, password_hash, full_name, role, status,
                auth_provider
            ) VALUES (
                :id, :email, :password_hash, :full_name, 'owner', 'invited',
                'password'
            )
            ON CONFLICT (email) DO NOTHING
            RETURNING id
            """
        ),
        {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "full_name": email.split("@", 1)[0][:120],
        },
    ).scalar_one_or_none()
    if inserted is None:
        raise SignupError(
            "signup_failed",
            "Unable to create an account with these details.",
            status_code=409,
        )

    issued = issue_token(session, user_id, email)
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
                    "purpose": "verify_email",
                    "user_id": str(user_id),
                    "email": email,
                    "token": issued["token"],
                }
            )
        },
    )
    return {"status": "pending_verification"}


__all__ = [
    "EMAIL_PATTERN",
    "MIN_PASSWORD_LENGTH",
    "SignupError",
    "hash_password",
    "signup",
]
