"""Immutable money value object in minor units."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in minor units paired with an ISO 4217 currency code."""

    amount_minor: int
    currency: str

    def validate(self) -> bool:
        return (
            isinstance(self.amount_minor, int)
            and not isinstance(self.amount_minor, bool)
            and isinstance(self.currency, str)
            and len(self.currency) == 3
            and self.currency.isalpha()
            and self.currency.isupper()
        )

    def _require(self) -> None:
        if not self.validate():
            raise ValueError(
                "Money requires an integer amount_minor and a three-letter "
                "uppercase currency code"
            )

    def add(self, other: Money) -> Money:
        if not isinstance(other, Money):
            raise TypeError("other must be a Money instance")
        self._require()
        other._require()
        self._require_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def subtract(self, other: Money) -> Money:
        if not isinstance(other, Money):
            raise TypeError("other must be a Money instance")
        self._require()
        other._require()
        self._require_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def multiply(self, factor: Decimal | int | float | str) -> Money:
        self._require()
        try:
            decimal_factor = Decimal(str(factor))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("factor must be a finite decimal") from exc
        if not decimal_factor.is_finite():
            raise ValueError("factor must be a finite decimal")
        amount = (Decimal(self.amount_minor) * decimal_factor).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return Money(int(amount), self.currency)

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("Money operations require the same currency")


def gross_margin_bp(price: Money, cost: Money) -> int:
    """Return gross margin in basis points, rounded half up."""

    if not isinstance(price, Money) or not isinstance(cost, Money):
        raise TypeError("price and cost must be Money instances")
    price._require()
    cost._require()
    price._require_same_currency(cost)
    if price.amount_minor <= 0:
        raise ValueError("price must be greater than zero")
    if cost.amount_minor < 0:
        raise ValueError("cost must not be negative")

    margin = Decimal(price.amount_minor - cost.amount_minor) * Decimal(10000)
    return int(
        (margin / Decimal(price.amount_minor)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


__all__ = ["Money", "gross_margin_bp"]
