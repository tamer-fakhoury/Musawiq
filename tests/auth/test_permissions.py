"""Permission matrix and authorization dependency contracts."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from musawiq.auth.errors import PermissionDenied
from musawiq.auth.permissions import Action, Role
from musawiq.auth.service import AuthorizationService, require
from musawiq.middleware.correlation import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
)
from musawiq.middleware.errors import install_error_handlers

OWNER_OR_MANAGER = {Role.OWNER, Role.MANAGER}


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("action", list(Action))
def test_every_role_action_cell(role: Role, action: Action) -> None:
    allowed = role in OWNER_OR_MANAGER or action is Action.READ

    if allowed:
        AuthorizationService().check(role, action)
    else:
        with pytest.raises(PermissionDenied):
            AuthorizationService().check(role, action)


def test_service_accepts_string_roles_and_actions() -> None:
    AuthorizationService().check("owner", "publish_page")

    with pytest.raises(PermissionDenied):
        AuthorizationService().check("analyst", "publish_page")


class RoleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.role = request.headers.get("X-Test-Role", "analyst")
        return await call_next(request)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/admin")
    def admin(_: None = Depends(require(Action.PUBLISH_PAGE))):
        return {"ok": True}

    app.add_middleware(RoleMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    with TestClient(app) as test_client:
        yield test_client


def test_denied_dependency_returns_403_envelope(client) -> None:
    response = client.get("/admin")

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "permission_denied"
    assert error["message"] == "You do not have permission to perform this action."
    assert error["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
    assert "admin" not in response.text.lower()


def test_allowed_dependency_passes(client) -> None:
    response = client.get("/admin", headers={"X-Test-Role": "owner"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
