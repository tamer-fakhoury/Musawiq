"""Authorization exceptions shared by the error envelope and auth service."""

from __future__ import annotations


class PermissionDenied(Exception):
    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to perform this action."

    def __init__(self, message: str | None = None) -> None:
        if message:
            self.message = message
        super().__init__(self.message)


__all__ = ["PermissionDenied"]
