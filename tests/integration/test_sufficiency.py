"""FR-2.1.3 data sufficiency assessment."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb
from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _create_concept(client, tenant, taxonomy) -> dict:
    category_id, niche_id = taxonomy
    response = client.post(
        "/product-concepts",
        json={
            "name": "Travel mug",
            "description": "Insulated stainless steel travel mug",
            "category_id": str(category_id),
            "niche_id": str(niche_id),
            "price_minor": 1000,
            "cost_minor": 400,
            "currency": "USD",
        },
        headers=_headers(tenant),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_orders(
    engine,
    tenant,
    *,
    count: int,
    first_days_ago: float,
    last_days_ago: float,
) -> None:
    now = datetime.now(timezone.utc)
    if count == 1:
        offsets = [first_days_ago]
    else:
        step = (first_days_ago - last_days_ago) / (count - 1)
        offsets = [first_days_ago - index * step for index in range(count)]
    with engine.begin() as conn:
        for offset in offsets:
            conn.execute(
                text(
                    """
                    INSERT INTO orders (
                        store_id, origin, status, currency, placed_at
                    ) VALUES (
                        :store_id, 'imported', 'fulfilled', 'USD', :placed_at
                    )
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "placed_at": now - timedelta(days=offset),
                },
            )


def _seed_audience(
    engine,
    tenant,
    niche_id: uuid.UUID,
    *,
    updated_at: datetime | None = None,
    locations: tuple[str, ...] = ("SA",),
    with_segment: bool = True,
) -> uuid.UUID:
    profile_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audience_profiles (
                    id, store_id, version, status, is_current,
                    niche_ids, languages, created_by, updated_at
                ) VALUES (
                    :id, :store_id, 1, 'active', true,
                    CAST(:niche_ids AS uuid[]), CAST(:languages AS text[]),
                    :created_by, :updated_at
                )
                """
            ),
            {
                "id": profile_id,
                "store_id": tenant.store_id,
                "niche_ids": [niche_id],
                "languages": ["en"],
                "created_by": tenant.user_id,
                "updated_at": updated_at or now,
            },
        )
        if with_segment:
            conn.execute(
                text(
                    """
                    INSERT INTO audience_segments (
                        store_id, audience_profile_id, label, locations,
                        age_min, age_max
                    ) VALUES (
                        :store_id, :profile_id, 'Core', :locations, 18, 40
                    )
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "profile_id": profile_id,
                    "locations": Jsonb(list(locations)),
                },
            )
    return profile_id


def _run(client, tenant, concept_id: str, body=None):
    return client.post(
        f"/product-concepts/{concept_id}/sufficiency-checks",
        json=body,
        headers=_headers(tenant),
    )


def _available_inputs(engine, tenant, taxonomy) -> None:
    _seed_orders(
        engine,
        tenant,
        count=20,
        first_days_ago=30,
        last_days_ago=0,
    )
    _seed_audience(engine, tenant, taxonomy[1])


def _assert_blocking(body, *inputs: str) -> None:
    assert body["blocking_reasons"] == list(inputs)


def test_available_inputs_persist_and_optional_competitive_is_missing(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _available_inputs(db_engine, tenant, taxonomy)

    response = _run(client, tenant, concept["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sales_history_status"] == "available"
    assert body["audience_status"] == "available"
    assert body["cost_price_status"] == "available"
    assert body["competitive_data_status"] == "missing"
    assert body["overall_status"] == "sufficient"
    assert body["blocking_reasons"] == []
    assert body["policy_version"] == "1"
    assert body["checked_at"] is not None

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT store_id, product_concept_id, sales_history_status,
                       audience_status, cost_price_status,
                       competitive_data_status, overall_status,
                       blocking_reasons, checked_at
                FROM sufficiency_checks WHERE id = :id
                """
            ),
            {"id": uuid.UUID(body["id"])},
        ).mappings().one()
    assert row["store_id"] == tenant.store_id
    assert row["product_concept_id"] == uuid.UUID(concept["id"])
    assert row["sales_history_status"] == "available"
    assert row["audience_status"] == "available"
    assert row["cost_price_status"] == "available"
    assert row["competitive_data_status"] == "missing"
    assert row["overall_status"] == "sufficient"
    assert row["blocking_reasons"] == []
    assert row["checked_at"] is not None

    latest = client.get(
        f"/product-concepts/{concept['id']}/sufficiency-checks/latest",
        headers=_headers(tenant),
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]
    assert latest.json()["overall_status"] == "sufficient"


def test_competitive_data_is_optional_and_never_blocks(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _available_inputs(db_engine, tenant, taxonomy)
    now = datetime.now(timezone.utc)

    fresh = _run(
        client,
        tenant,
        concept["id"],
        {
            "competitive_data": {
                "observed_at": now.isoformat(),
                "items": [{"source": "market"}],
            }
        },
    ).json()
    assert fresh["competitive_data_status"] == "available"
    assert fresh["overall_status"] == "sufficient"
    assert fresh["blocking_reasons"] == []

    stale = _run(
        client,
        tenant,
        concept["id"],
        {
            "competitive_data": {
                "observed_at": (
                    now - timedelta(days=200)
                ).isoformat(),
                "items": [{"source": "market"}],
            }
        },
    ).json()
    assert stale["competitive_data_status"] == "stale"
    assert stale["overall_status"] == "sufficient"
    assert stale["blocking_reasons"] == []


def test_missing_critical_inputs_are_not_imputed(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)

    response = _run(client, tenant, concept["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sales_history_status"] == "missing"
    assert body["audience_status"] == "missing"
    assert body["cost_price_status"] == "available"
    assert body["competitive_data_status"] == "missing"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "sales_history", "audience")

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT blocking_reasons FROM sufficiency_checks
                WHERE id = :id
                """
            ),
            {"id": uuid.UUID(body["id"])},
        ).mappings().one()
    assert row["blocking_reasons"] == ["sales_history", "audience"]


def test_sales_history_insufficient_volume(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _seed_orders(
        db_engine,
        tenant,
        count=5,
        first_days_ago=30,
        last_days_ago=0,
    )
    _seed_audience(db_engine, tenant, taxonomy[1])

    body = _run(client, tenant, concept["id"]).json()
    assert body["sales_history_status"] == "insufficient"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "sales_history")


def test_sales_history_insufficient_period(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _seed_orders(
        db_engine,
        tenant,
        count=20,
        first_days_ago=5,
        last_days_ago=0,
    )
    _seed_audience(db_engine, tenant, taxonomy[1])

    body = _run(client, tenant, concept["id"]).json()
    assert body["sales_history_status"] == "insufficient"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "sales_history")


def test_sales_history_stale(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _seed_orders(
        db_engine,
        tenant,
        count=20,
        first_days_ago=130,
        last_days_ago=100,
    )
    _seed_audience(db_engine, tenant, taxonomy[1])

    body = _run(client, tenant, concept["id"]).json()
    assert body["sales_history_status"] == "stale"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "sales_history")


def test_audience_incomplete_without_segments(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _seed_orders(
        db_engine,
        tenant,
        count=20,
        first_days_ago=30,
        last_days_ago=0,
    )
    _seed_audience(
        db_engine,
        tenant,
        taxonomy[1],
        with_segment=False,
    )

    body = _run(client, tenant, concept["id"]).json()
    assert body["audience_status"] == "insufficient"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "audience")


def test_audience_incomplete_without_locations(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _seed_orders(
        db_engine,
        tenant,
        count=20,
        first_days_ago=30,
        last_days_ago=0,
    )
    _seed_audience(
        db_engine,
        tenant,
        taxonomy[1],
        locations=(),
    )

    body = _run(client, tenant, concept["id"]).json()
    assert body["audience_status"] == "insufficient"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "audience")


def test_audience_stale(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _seed_orders(
        db_engine,
        tenant,
        count=20,
        first_days_ago=30,
        last_days_ago=0,
    )
    _seed_audience(
        db_engine,
        tenant,
        taxonomy[1],
        updated_at=datetime.now(timezone.utc) - timedelta(days=200),
    )

    body = _run(client, tenant, concept["id"]).json()
    assert body["audience_status"] == "stale"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "audience")


def test_cost_price_insufficient(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    _available_inputs(db_engine, tenant, taxonomy)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE product_concepts SET price_minor = 0 WHERE id = :id"
            ),
            {"id": uuid.UUID(concept["id"])},
        )

    body = _run(client, tenant, concept["id"]).json()
    assert body["sales_history_status"] == "available"
    assert body["audience_status"] == "available"
    assert body["cost_price_status"] == "insufficient"
    assert body["overall_status"] == "insufficient"
    _assert_blocking(body, "cost_price")


def test_sufficiency_is_scoped_to_the_caller_store(
    client, tenant, make_tenant, taxonomy
) -> None:
    concept = _create_concept(client, tenant, taxonomy)
    other = make_tenant()

    response = client.post(
        f"/product-concepts/{concept['id']}/sufficiency-checks",
        headers=_headers(other),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
