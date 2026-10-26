"""AI training policy."""

from __future__ import annotations


def training_allowed(store_settings: dict) -> bool:
    """Return true only for an explicit boolean opt-in."""
    return store_settings.get("ai_training_opt_in") is True


__all__ = ["training_allowed"]
