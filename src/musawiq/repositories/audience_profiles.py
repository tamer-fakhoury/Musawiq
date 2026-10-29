"""Tenant-scoped audience profile reads for sufficiency assessment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from musawiq.repositories.base import TenantScopedRepository


@dataclass(frozen=True, slots=True)
class AudienceSnapshot:
    """Current audience profile and its segments."""

    profile: Mapping[str, object] | None
    segments: tuple[Mapping[str, object], ...]


class AudienceProfileRepository(TenantScopedRepository):
    """Repository for the current audience profile."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, "audience_profiles")

    def current_with_segments(self) -> AudienceSnapshot:
        tenant = self._tenant()
        profile = self.session.execute(
            text(
                """
                SELECT * FROM public.audience_profiles
                WHERE store_id = :store_id AND is_current
                LIMIT 1
                """
            ),
            {"store_id": tenant.store_id},
        ).mappings().one_or_none()
        if profile is None:
            return AudienceSnapshot(profile=None, segments=())
        segments = self.session.execute(
            text(
                """
                SELECT * FROM public.audience_segments
                WHERE store_id = :store_id
                  AND audience_profile_id = :profile_id
                ORDER BY created_at, id
                """
            ),
            {
                "store_id": tenant.store_id,
                "profile_id": profile["id"],
            },
        ).mappings().all()
        return AudienceSnapshot(
            profile=profile,
            segments=tuple(segments),
        )


__all__ = ["AudienceProfileRepository", "AudienceSnapshot"]
