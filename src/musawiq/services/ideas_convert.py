"""Explicit idea-to-concept conversion with bidirectional traceability."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from musawiq.db.tenant import TenantContext
from musawiq.repositories.product_ideas import ProductIdeaRepository
from musawiq.services.concepts import (
    ConceptValidationError,
    create_concept,
    get_concept,
)


class IdeaConversionError(Exception):
    """Base class for idea conversion failures."""


class IdeaConversionNotFound(IdeaConversionError):
    """Raised when the idea is outside the active store."""


class ConversionConfirmationRequired(IdeaConversionError):
    """Raised when the merchant did not confirm conversion."""


def convert_idea(
    session: Session,
    tenant: TenantContext,
    idea_id: uuid.UUID | str,
    payload: Mapping[str, Any],
    *,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Create a draft concept from an idea, once, in one transaction."""

    if not confirmed:
        raise ConversionConfirmationRequired(
            "Conversion requires explicit confirmation."
        )

    repository = ProductIdeaRepository(session)
    try:
        idea = repository.get_idea(idea_id)
    except ValueError as exc:
        raise IdeaConversionNotFound("Product idea not found") from exc
    if idea is None:
        raise IdeaConversionNotFound("Product idea not found")

    if idea["state"] == "converted":
        if idea["converted_concept_id"] is None:
            raise IdeaConversionError(
                "Converted idea has no linked product concept."
            )
        return get_concept(
            session, tenant, idea["converted_concept_id"]
        )
    if idea["state"] == "dismissed":
        raise IdeaConversionError(
            "Dismissed ideas must be restored before conversion."
        )

    concept_payload = {
        "name": payload.get("name", idea["name"]),
        "description": payload.get("description", idea["description"]),
        "category_id": payload.get("category_id", idea["category_id"]),
        "niche_id": payload.get("niche_id", idea["niche_id"]),
        "price_minor": payload.get("price_minor"),
        "cost_minor": payload.get("cost_minor"),
        "currency": payload.get("currency"),
    }

    try:
        concept = create_concept(
            session,
            tenant,
            concept_payload,
            source_idea_id=idea["id"],
        )
        updated = repository.update_idea(
            idea_id,
            {
                "state": "converted",
                "converted_concept_id": concept["id"],
            },
        )
        if updated is None:
            raise IdeaConversionNotFound("Product idea not found")
    except ConceptValidationError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    return concept


__all__ = [
    "ConversionConfirmationRequired",
    "IdeaConversionError",
    "IdeaConversionNotFound",
    "convert_idea",
]
