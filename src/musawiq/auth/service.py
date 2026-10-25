"""Server-side authorization checks and FastAPI dependency factory."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from musawiq.auth.errors import PermissionDenied
from musawiq.auth.permissions import Action, Role, is_allowed


class AuthorizationService:
    def check(self, role: Role | str, action: Action | str) -> None:
        if not is_allowed(role, action):
            raise PermissionDenied()


def require(action: Action | str) -> Callable[[Request], None]:
    action_value = Action(action)

    def dependency(request: Request) -> None:
        role = getattr(request.state, "role", None)
        if role is None:
            raise PermissionDenied()
        AuthorizationService().check(role, action_value)

    return dependency


__all__ = ["AuthorizationService", "PermissionDenied", "require"]
