"""FR-5.1.3: versioned decision rule configuration."""

from __future__ import annotations

from sqlalchemy import text


def _headers(site):
    return {
        "X-Store-Id": str(site.store_id),
        "X-User-Id": str(site.user_id),
        "X-User-Role": "owner",
    }


def _rule_payload(**overrides):
    payload = {
        "min_spend_minor": 10000,
        "min_clicks": 100,
        "min_conversions": 5,
        "min_confirmed_deposits": 2,
        "min_conversion_rate": 0.02,
        "max_cost_per_conversion_minor": 5000,
        "rules": {"schema_version": 1, "note": "initial"},
    }
    payload.update(overrides)
    return payload


def _create(client, site, payload):
    return client.post(
        "/decision-rule-sets", json=payload, headers=_headers(site)
    )


def _resolved(client, site, category_id=None):
    params = {"category_id": str(category_id)} if category_id else {}
    return client.get(
        "/decision-rule-sets/resolved", params=params, headers=_headers(site)
    )


def _category(db_engine, site):
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT category_id FROM product_concepts WHERE store_id = :id"
            ),
            {"id": site.store_id},
        ).scalar_one()


def test_each_save_versions_and_audits(client, site, db_engine):
    first = _create(client, site, _rule_payload())
    assert first.status_code == 201
    assert first.json()["version"] == 1
    assert first.json()["is_active"] is True

    second = _create(
        client, site, _rule_payload(min_conversion_rate=0.05)
    )
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["is_active"] is True

    listed = client.get("/decision-rule-sets", headers=_headers(site))
    versions = listed.json()
    assert [(item["version"], item["is_active"]) for item in versions] == [
        (2, True),
        (1, False),
    ]

    with db_engine.connect() as conn:
        audits = conn.execute(
            text(
                "SELECT action, before, after FROM audit_logs "
                "WHERE target_type = 'decision_rule_set' "
                "AND store_id = :store_id ORDER BY created_at, id"
            ),
            {"store_id": site.store_id},
        ).mappings().all()
    assert [row["action"] for row in audits] == [
        "decision_rule_set.updated",
        "decision_rule_set.updated",
    ]
    assert audits[1]["before"]["version"] == 1
    assert audits[1]["after"]["version"] == 2
    assert audits[1]["after"]["min_conversion_rate"] == 0.05


def test_invalid_rules_are_rejected(client, site):
    missing_schema = _create(
        client, site, _rule_payload(rules={"note": "no schema"})
    )
    assert missing_schema.status_code == 422
    assert missing_schema.json()["error"]["code"] == "invalid_rules"

    negative = _create(client, site, _rule_payload(min_spend_minor=-1))
    assert negative.status_code == 422
    assert negative.json()["error"]["code"] == "invalid_min_spend_minor"

    bad_rate = _create(client, site, _rule_payload(min_conversion_rate=2))
    assert bad_rate.status_code == 422
    assert bad_rate.json()["error"]["code"] == "invalid_min_conversion_rate"


def test_resolution_prefers_category_then_store_then_platform(
    client, site, db_engine
):
    platform = _resolved(client, site)
    assert platform.status_code == 404

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO decision_rule_sets (
                    store_id, category_id, version, is_active,
                    min_spend_minor, min_clicks, min_conversions,
                    min_conversion_rate, max_cost_per_conversion_minor,
                    rules
                ) VALUES (
                    NULL, NULL, 1, true, 1000, 10, 2, 0.01, 4000,
                    '{"schema_version": 1, "scope": "platform"}'::jsonb
                )
                """
            )
        )
    platform = _resolved(client, site)
    assert platform.status_code == 200
    assert platform.json()["scope"] == "platform"
    assert platform.json()["version"] == 1

    store_rule = _create(client, site, _rule_payload(min_clicks=120))
    assert store_rule.status_code == 201
    store_resolved = _resolved(client, site)
    assert store_resolved.json()["scope"] == "store"
    assert store_resolved.json()["min_clicks"] == 120

    category_id = _category(db_engine, site)
    category_rule = _create(
        client,
        site,
        _rule_payload(category_id=str(category_id), min_clicks=200),
    )
    assert category_rule.status_code == 201
    category_resolved = _resolved(client, site, category_id)
    body = category_resolved.json()
    assert body["scope"] == "category"
    assert body["category_id"] == str(category_id)
    assert body["min_clicks"] == 200
    assert set(body) >= {
        "version",
        "min_conversion_rate",
        "max_cost_per_conversion_minor",
        "rules",
    }
