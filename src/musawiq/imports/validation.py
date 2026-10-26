"""Pure row validation and dedupe hashing for imports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_REQUIRED_ORDER = (
    "product_id",
    "product_name",
    "order_date",
    "quantity",
    "sales_amount",
)
_CURRENCY = re.compile(r"^[A-Za-z]{3}$")


@dataclass(frozen=True)
class Issue:
    field: str
    code: str
    message: str
    raw_value: str


def _raw(row: dict[str, str], mapping: dict[str, str], target: str) -> str:
    source = mapping.get(target)
    if source is None:
        return ""
    value = row.get(source)
    return "" if value is None else str(value).strip()


def _parse_date(value: str, tz: ZoneInfo) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _parse_decimal(value: str) -> Decimal:
    amount = Decimal(value)
    if not amount.is_finite():
        raise InvalidOperation
    return amount


def _decimal_text(value: object) -> str:
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        decimal_value = Decimal(str(value))
    return format(decimal_value.normalize(), "f")


def _date_text(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat().lower()
    return str(value).strip().lower()


def _text(value: object) -> str:
    return str(value).strip().lower()


def validate_row(
    row: dict[str, str],
    mapping: dict[str, str],
    *,
    timezone: str,
    default_currency: str,
) -> tuple[dict, list[Issue]]:
    """Map and validate one CSV-style row. Unknown columns are ignored."""
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {timezone!r}") from exc

    issues: list[Issue] = []
    normalized: dict[str, object] = {}

    for target in _REQUIRED_ORDER:
        value = _raw(row, mapping, target)
        if not value:
            issues.append(
                Issue(target, "required", "is required", value)
            )
            continue

        if target == "order_date":
            try:
                normalized[target] = _parse_date(value, tz)
            except (ValueError, TypeError):
                issues.append(
                    Issue(target, "invalid_date", "must be a valid date", value)
                )
        elif target == "quantity":
            try:
                quantity = int(value)
            except ValueError:
                quantity = 0
            if quantity <= 0:
                issues.append(
                    Issue(
                        target,
                        "invalid_quantity",
                        "must be an integer greater than zero",
                        value,
                    )
                )
            else:
                normalized[target] = quantity
        elif target == "sales_amount":
            try:
                amount = _parse_decimal(value)
            except (InvalidOperation, ValueError):
                amount = Decimal("-1")
            if amount < 0:
                issues.append(
                    Issue(
                        target,
                        "invalid_amount",
                        "must be a non-negative decimal",
                        value,
                    )
                )
            else:
                normalized[target] = amount
        else:
            normalized[target] = value

    order_id = _raw(row, mapping, "order_id")
    if order_id:
        normalized["order_id"] = order_id

    sku = _raw(row, mapping, "sku")
    if sku:
        normalized["sku"] = sku

    provided_currency = _raw(row, mapping, "currency")
    currency = provided_currency or str(default_currency).strip()
    if _CURRENCY.fullmatch(currency):
        normalized["currency"] = currency.upper()
    else:
        issues.append(
            Issue(
                "currency",
                "invalid_currency",
                "must be a 3-letter ISO currency code",
                currency,
            )
        )

    return normalized, issues


def dedupe_hash(normalized: dict) -> str:
    """Return the stable SHA-256 duplicate key for a normalized row."""
    order_id = normalized.get("order_id")
    if order_id is not None and str(order_id).strip():
        payload = "|".join(
            (
                _text(order_id),
                _text(normalized.get("product_id", "")),
            )
        )
    else:
        product = (
            normalized.get("product_id")
            or normalized.get("product_name")
            or ""
        )
        payload = "|".join(
            (
                _text(product),
                _date_text(normalized.get("order_date", "")),
                _text(normalized.get("quantity", "")),
                _decimal_text(normalized.get("sales_amount", Decimal("0"))),
            )
        )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "Issue",
    "dedupe_hash",
    "validate_row",
]
