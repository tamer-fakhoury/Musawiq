"""Role and action permission matrix."""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    ANALYST = "analyst"


class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    PUBLISH_PAGE = "publish_page"
    SUBMIT_CAMPAIGN = "submit_campaign"
    APPROVE_BUDGET = "approve_budget"
    EXTEND_TEST = "extend_test"
    ACCEPT_RECOMMENDATION = "accept_recommendation"


ALL_ACTIONS = frozenset(Action)

PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.OWNER: ALL_ACTIONS,
    Role.MANAGER: ALL_ACTIONS,
    Role.ANALYST: frozenset({Action.READ}),
}


def is_allowed(role: Role | str, action: Action | str) -> bool:
    try:
        role_value = Role(role)
        action_value = Action(action)
    except ValueError:
        return False
    return action_value in PERMISSIONS[role_value]


__all__ = [
    "ALL_ACTIONS",
    "Action",
    "PERMISSIONS",
    "Role",
    "is_allowed",
]
