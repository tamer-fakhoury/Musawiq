"""FR-8.8b - run the AI marketing feedback loop end to end.

Steps:
  1. ingest a weak 7-day signal window
  2. run an AI analysis (issues + recommendations, Arabic)
  3. apply improved Arabic copy to the demo variations
  4. ingest an improved 7-day signal window
  5. run a second analysis and compute the before/after delta

Writes a readable report to var/demo_report.md (UTF-8) and prints a short
summary. Requires scripts.demo_seed to have been run first.

Usage:
    python -m scripts.demo_flow --provider fixture
    python -m scripts.demo_flow --provider groq
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from musawiq.ai.analysis import service as analysis_service  # noqa: E402
from musawiq.ai.analysis.delta import compute_delta, summarize_delta  # noqa: E402
from musawiq.ai.providers.factory import get_provider  # noqa: E402
from musawiq.config import get_settings  # noqa: E402
from musawiq.db.session import get_session_factory  # noqa: E402
from musawiq.db.tenant import set_local_tenant  # noqa: E402
from musawiq.services import campaigns as campaign_service  # noqa: E402
from musawiq.services import signals as signal_service  # noqa: E402

IMPROVED_COPY = [
    (
        "عباية صيفية خفيفة تتنفس معك طول اليوم",
        "خامة قطنية باردة، قصّة واسعة، وتوصيل مجاني داخل السعودية. "
        "اطلبي الآن عبر واتساب والدفع عند الاستلام.",
        "خصم 15% لأول 50 طلب",
    ),
    (
        "أناقة بلا حرارة: عباية تكتمل بها إطلالتك",
        "خفيفة على الجسم، لا تشفّ، ومناسبة للدوام والمناسبات. "
        "متوفرة الآن بثلاث درجات، والطلب عبر واتساب مباشرة.",
        "توصيل خلال يومين",
    ),
    (
        "عبايتك الصيفية بلمسة عصرية",
        "قماش يتنفس وملمس ناعم، مع خيارات مقاسات واسعة. "
        "الدفع عند الاستلام، والتوصيل مجاني داخل المملكة.",
        "ضمان استبدال المقاس",
    ),
]


def _window(days_back_start: int, days_back_end: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (
        now - timedelta(days=days_back_start),
        now - timedelta(days=days_back_end),
    )


def _signal_payload(
    variations: list[dict],
    start: datetime,
    end: datetime,
    *,
    impressions: int,
    clicks: int,
    conversions: int,
) -> dict:
    rows = []
    per_ad = max(1, len(variations))
    for variation in variations:
        rows.append(
            {
                "ad_variation_id": variation["id"],
                "impressions": impressions // per_ad,
                "reach": int(impressions * 0.75) // per_ad,
                "clicks": clicks // per_ad,
                "spend_minor": 12000 // per_ad,
                "conversions": conversions // per_ad,
            }
        )
    return {
        "period_start": start,
        "period_end": end,
        "provider": "meta",
        "rows": rows,
    }


def _metrics_snapshot(analysis: dict) -> dict:
    signals = (analysis.get("input_snapshot") or {}).get("signals") or {}
    metrics = signals.get("totals") or {}
    return {
        key: metrics.get(key)
        for key in (
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
    }


def _render_report(
    poor: dict, improved: dict, delta_rows: list[dict], summary: dict
) -> str:
    lines: list[str] = ["# تقرير تجربة الحلقة الذكية", ""]

    for title, analysis in (("التحليل الأول (إشارات ضعيفة)", poor), ("التحليل الثاني (بعد التعديل)", improved)):
        lines.append(f"## {title}")
        lines.append("")
        if analysis.get("status") != "succeeded":
            lines.append(f"- الحالة: {analysis.get('status')}")
            lines.append("- لم يتم إنتاج تحليل. تأكد من إعداد مفتاح مزود الذكاء الاصطناعي.")
            lines.append("")
            continue
        result = analysis.get("result") or {}
        demand = result.get("demand") or {}
        lines.append(f"- مستوى الطلب: **{demand.get('level')}** (ثقة {demand.get('confidence')})")
        lines.append(f"- التبرير: {demand.get('rationale_ar')}")
        issues = result.get("issues") or []
        lines.append(f"- عدد الملاحظات: {len(issues)}")
        for issue in issues:
            lines.append(
                f"  - [{issue.get('type')}/{issue.get('severity')}] "
                f"{issue.get('rationale_ar')} "
                f"(المؤشر {issue.get('metric')} = {issue.get('observed')})"
            )
        recs = result.get("recommendations") or []
        lines.append(f"- عدد التوصيات: {len(recs)}")
        for rec in recs:
            lines.append(f"  - {rec.get('action')}: {rec.get('change_ar')}")
            if rec.get("copy_paste_ar"):
                lines.append(f"    > {rec.get('copy_paste_ar')}")
        steps = result.get("next_steps_ar") or []
        if steps:
            lines.append("- الخطوات التالية:")
            for step in steps:
                lines.append(f"  - {step}")
        lines.append("")

    lines.append("## أثر التعديلات")
    lines.append("")
    lines.append(f"- ملخص: **{summary.get('headline')}** "
                 f"(تحسن {summary.get('improved')}، تراجع {summary.get('degraded')}، ثابت {summary.get('flat')})")
    lines.append("")
    lines.append("| المؤشر | قبل | بعد | التغير % | الاتجاه |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in delta_rows:
        lines.append(
            f"| {row['metric']} | {row['before']} | {row['after']} | "
            f"{row['change_pct']} | {row['direction']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["fixture", "groq", "openai"], default="fixture")
    args = parser.parse_args()

    ids_path = ROOT / "var" / "demo_ids.json"
    if not ids_path.exists():
        print("Run `python -m scripts.demo_seed` first.", file=sys.stderr)
        return 2
    ids = json.loads(ids_path.read_text(encoding="utf-8"))

    settings = get_settings().model_copy(update={"ai_provider": args.provider})
    provider = get_provider(settings)

    session = get_session_factory()()
    tenant = set_local_tenant(
        session, ids["store_id"], ids["user_id"], "owner"
    )
    try:
        campaign = campaign_service.get_campaign(
            session, tenant, ids["campaign_id"]
        )
        variations = [
            variation
            for ad_set in campaign.get("ad_sets") or []
            for variation in ad_set.get("variations") or []
        ]
        if not variations:
            print("Demo campaign has no variations; rerun demo_seed.", file=sys.stderr)
            return 2

        poor_start, poor_end = _window(14, 7)
        signal_service.write_signals(
            session,
            tenant,
            campaign,
            _signal_payload(
                variations, poor_start, poor_end,
                impressions=24000, clicks=144, conversions=1,
            ),
        )

        print(f"provider: {provider.provider} available={provider.available}")
        poor = analysis_service.create_analysis(
            session,
            tenant,
            ids["campaign_id"],
            window_start=poor_start,
            window_end=poor_end,
            provider=provider,
        )

        for variation, (headline, copy_text, description) in zip(
            variations, IMPROVED_COPY
        ):
            campaign_service.update_variation(
                session,
                tenant,
                variation["id"],
                {
                    "headline": headline,
                    "copy_text": copy_text,
                    "description": description,
                },
            )

        good_start, good_end = _window(7, 0)
        signal_service.write_signals(
            session,
            tenant,
            campaign,
            _signal_payload(
                variations, good_start, good_end,
                impressions=26000, clicks=780, conversions=10,
            ),
        )

        improved = analysis_service.create_analysis(
            session,
            tenant,
            ids["campaign_id"],
            window_start=good_start,
            window_end=good_end,
            provider=provider,
        )

        session.commit()

        delta_rows = compute_delta(
            _metrics_snapshot(poor), _metrics_snapshot(improved)
        )
        summary = summarize_delta(delta_rows)

        report = _render_report(poor, improved, delta_rows, summary)
        out = ROOT / "var" / "demo_report.md"
        out.write_text(report, encoding="utf-8")

        print(f"analysis 1: status={poor['status']} demand={poor.get('demand_level')}")
        print(f"analysis 2: status={improved['status']} demand={improved.get('demand_level')}")
        print(f"delta headline: {summary['headline']} "
              f"(improved={summary['improved']}, degraded={summary['degraded']}, flat={summary['flat']})")
        print(f"report: {out}")

        if poor["status"] != "succeeded" or improved["status"] != "succeeded":
            print("AI provider was degraded. Set MUSAWIQ_GROQ_API_KEY (or MUSAWIQ_OPENAI_API_KEY), "
                  "or rerun with --provider fixture for the offline proof.", file=sys.stderr)
            return 3
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
