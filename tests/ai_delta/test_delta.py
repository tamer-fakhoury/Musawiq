"""Re-evaluation delta computation contracts."""

from __future__ import annotations

from musawiq.ai.analysis.delta import compute_delta, summarize_delta


def _metric(deltas: list[dict], name: str) -> dict:
    return next(delta for delta in deltas if delta["metric"] == name)


def test_ctr_up_is_improved():
    deltas = compute_delta({"ctr": 1.0}, {"ctr": 2.0})

    ctr = _metric(deltas, "ctr")
    assert ctr == {
        "metric": "ctr",
        "before": 1.0,
        "after": 2.0,
        "change_abs": 1.0,
        "change_pct": 100.0,
        "direction": "improved",
    }
    assert summarize_delta([ctr]) == {
        "improved": 1,
        "degraded": 0,
        "flat": 0,
        "headline": "improved",
    }


def test_cpc_up_is_degraded():
    deltas = compute_delta({"cpc_minor": 100.0}, {"cpc_minor": 150.0})

    cpc = _metric(deltas, "cpc_minor")
    assert cpc["direction"] == "degraded"
    assert cpc["change_abs"] == 50.0
    assert cpc["change_pct"] == 50.0
    assert summarize_delta([cpc]) == {
        "improved": 0,
        "degraded": 1,
        "flat": 0,
        "headline": "degraded",
    }


def test_under_two_percent_is_flat():
    flat = _metric(
        compute_delta({"ctr": 100.0}, {"ctr": 101.0}),
        "ctr",
    )
    assert flat["change_pct"] == 1.0
    assert flat["direction"] == "flat"

    boundary = _metric(
        compute_delta({"ctr": 100.0}, {"ctr": 102.0}),
        "ctr",
    )
    assert boundary["change_pct"] == 2.0
    assert boundary["direction"] == "improved"


def test_missing_side_is_flat_without_percentage():
    deltas = compute_delta({"impressions": None}, {"impressions": 100.0})

    impressions = _metric(deltas, "impressions")
    assert impressions["before"] is None
    assert impressions["after"] == 100.0
    assert impressions["change_abs"] is None
    assert impressions["change_pct"] is None
    assert impressions["direction"] == "flat"
    assert summarize_delta([impressions])["headline"] == "flat"
