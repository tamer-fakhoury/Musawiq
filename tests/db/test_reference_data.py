"""Reference data tables and canonical seed (DB-0.3)."""

from __future__ import annotations

from sqlalchemy import text

EXPECTED_COUNTS = {
    "countries": 14,
    "currencies": 14,
    "languages": 4,
    "ad_platforms": 4,
    "event_types": 7,
}

EVENT_TYPE_CODES = {
    "page_view",
    "product_view",
    "cta_click",
    "whatsapp_click",
    "cod_form_start",
    "cod_order_submitted",
    "deposit_confirmed",
}


def test_seed_row_counts(conn):
    for table, expected in EXPECTED_COUNTS.items():
        actual = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        assert actual == expected, table


def test_language_direction_values(conn):
    directions = set(
        conn.execute(text("SELECT DISTINCT direction FROM languages")).scalars()
    )
    assert directions == {"ltr", "rtl"}


def test_currency_minor_units(conn):
    units = dict(
        conn.execute(
            text("SELECT code, minor_unit FROM currencies WHERE code IN ('KWD', 'JPY')")
        ).all()
    )
    assert units == {"KWD": 3, "JPY": 0}


def test_event_type_codes(conn):
    codes = set(conn.execute(text("SELECT code FROM event_types")).scalars())
    assert codes == EVENT_TYPE_CODES
    assert len(codes) == 7
