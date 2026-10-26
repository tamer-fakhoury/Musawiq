"""Pure metric delta and headline helpers for re-evaluation."""

from __future__ import annotations

SUPPORTED_METRICS: tuple[str, ...] = (
    "impressions",
    "reach",
    "clicks",
    "spend_minor",
    "ctr",
    "cpc_minor",
    "cpm_minor",
    "conversions",
    "cost_per_conversion_minor",
)

HIGHER_IS_BETTER = frozenset(
    {"ctr", "conversions", "reach", "impressions", "clicks"}
)
LOWER_IS_BETTER = frozenset(
    {"cpc_minor", "cpm_minor", "cost_per_conversion_minor"}
)
FLAT_THRESHOLD_PCT = 2.0


def _direction(
    metric: str,
    before: float | None,
    after: float | None,
    change_abs: float | None,
    change_pct: float | None,
) -> str:
    if before is None or after is None or change_abs is None:
        return "flat"
    if change_abs == 0:
        return "flat"
    if change_pct is not None and abs(change_pct) < FLAT_THRESHOLD_PCT:
        return "flat"
    if metric in HIGHER_IS_BETTER:
        return "improved" if change_abs > 0 else "degraded"
    if metric in LOWER_IS_BETTER:
        return "improved" if change_abs < 0 else "degraded"
    return "flat"


def compute_delta(
    previous: dict[str, float | None],
    current: dict[str, float | None],
) -> list[dict]:
    """Return one delta row per supported metric.

    Missing metrics are treated as ``None``. ``change_pct`` is ``None`` when
    ``before`` is missing or zero. A change is flat when either side is missing,
    when there is no absolute change, or when the absolute percentage change is
    strictly below 2%. The neutral metric ``spend_minor`` is always flat.
    """
    deltas: list[dict] = []
    for metric in SUPPORTED_METRICS:
        before = previous.get(metric)
        after = current.get(metric)
        if before is None or after is None:
            change_abs = None
            change_pct = None
        else:
            change_abs = after - before
            change_pct = (
                None if before == 0 else (change_abs / before) * 100.0
            )

        deltas.append(
            {
                "metric": metric,
                "before": before,
                "after": after,
                "change_abs": change_abs,
                "change_pct": change_pct,
                "direction": _direction(
                    metric, before, after, change_abs, change_pct
                ),
            }
        )
    return deltas


def summarize_delta(deltas: list[dict]) -> dict:
    """Count directions and pick one headline.

    ``improved`` requires at least one improved metric and zero degraded
    metrics. ``degraded`` is the mirror rule. With neither, the headline is
    ``flat``. Any list containing both improved and degraded metrics is
    ``mixed``, even when one side is larger.
    """
    improved = 0
    degraded = 0
    flat = 0
    for delta in deltas:
        direction = delta.get("direction")
        if direction == "improved":
            improved += 1
        elif direction == "degraded":
            degraded += 1
        else:
            flat += 1

    if degraded == 0 and improved > 0:
        headline = "improved"
    elif improved == 0 and degraded > 0:
        headline = "degraded"
    elif improved == 0 and degraded == 0:
        headline = "flat"
    else:
        headline = "mixed"

    return {
        "improved": improved,
        "degraded": degraded,
        "flat": flat,
        "headline": headline,
    }


__all__ = [
    "FLAT_THRESHOLD_PCT",
    "HIGHER_IS_BETTER",
    "LOWER_IS_BETTER",
    "SUPPORTED_METRICS",
    "compute_delta",
    "summarize_delta",
]
