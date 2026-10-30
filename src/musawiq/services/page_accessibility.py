"""Pre-publish accessibility baseline for generated landing pages (WCAG AA)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MIN_CONTRAST = 4.5


def _channel(value: str) -> tuple[float, float, float]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        raise ValueError(value)
    return tuple(int(text[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _luminance(rgb: tuple[float, float, float]) -> float:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(part) for part in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    first = _luminance(_channel(foreground))
    second = _luminance(_channel(background))
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def check(
    *,
    content: Mapping[str, Any],
    template_schema: Mapping[str, Any],
    channel: Mapping[str, Any] | None,
) -> list[str]:
    """Return human-readable accessibility failures (empty means pass)."""
    errors: list[str] = []

    product = content.get("product") or {}
    images = content.get("images")
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, Mapping) or not str(image.get("alt") or "").strip():
                errors.append("every image requires non-empty alt text")
                break
    elif product.get("image_file_ids"):
        errors.append("every image requires non-empty alt text")

    if channel and channel.get("type") == "cod":
        fields = (channel.get("cod_form_schema") or {}).get("fields") or []
        for field in fields:
            if not isinstance(field, Mapping) or not str(field.get("label") or "").strip():
                errors.append("every COD form field requires a label")
                break

    palette = template_schema.get("palette") or {}
    try:
        text_ratio = contrast_ratio(
            palette.get("text", "#111111"), palette.get("background", "#FFFFFF")
        )
        cta_ratio = contrast_ratio(
            palette.get("cta_text", "#FFFFFF"),
            palette.get("cta_background", "#111111"),
        )
    except ValueError:
        errors.append("template palette colours must be valid hex values")
    else:
        if text_ratio < MIN_CONTRAST:
            errors.append("body text contrast must meet WCAG AA (4.5:1)")
        if cta_ratio < MIN_CONTRAST:
            errors.append("CTA contrast must meet WCAG AA (4.5:1)")

    return errors


__all__ = ["MIN_CONTRAST", "check", "contrast_ratio"]
