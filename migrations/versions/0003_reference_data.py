"""DB-0.3 - reference data tables and seed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25

Creates the reference-data tables (countries, currencies, languages, ad_platforms,
event_types) and seeds them idempotently. These tables use natural ``code``
primary keys and carry no surrogate id or timestamps, per the documented
reference-data exception. Downgrade drops the five tables.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE countries (
            code char(2) PRIMARY KEY,
            name text NOT NULL,
            is_active boolean NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE currencies (
            code char(3) PRIMARY KEY,
            name text NOT NULL,
            minor_unit smallint NOT NULL,
            is_active boolean NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE languages (
            code text PRIMARY KEY,
            name text NOT NULL,
            direction text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            CONSTRAINT ck_languages_direction CHECK (direction IN ('ltr', 'rtl'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ad_platforms (
            code text PRIMARY KEY,
            name text NOT NULL,
            is_active boolean NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE event_types (
            code text PRIMARY KEY,
            description text NOT NULL,
            is_active boolean NOT NULL DEFAULT true
        )
        """
    )

    op.execute(
        """
        INSERT INTO countries (code, name, is_active) VALUES
            ('SA', 'Saudi Arabia', true),
            ('AE', 'United Arab Emirates', true),
            ('EG', 'Egypt', true),
            ('KW', 'Kuwait', true),
            ('BH', 'Bahrain', true),
            ('QA', 'Qatar', true),
            ('OM', 'Oman', true),
            ('JO', 'Jordan', true),
            ('MA', 'Morocco', true),
            ('US', 'United States', true),
            ('GB', 'United Kingdom', true),
            ('DE', 'Germany', true),
            ('FR', 'France', true),
            ('TR', 'Turkey', true)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO currencies (code, name, minor_unit, is_active) VALUES
            ('USD', 'US Dollar', 2, true),
            ('EUR', 'Euro', 2, true),
            ('GBP', 'Pound Sterling', 2, true),
            ('SAR', 'Saudi Riyal', 2, true),
            ('AED', 'UAE Dirham', 2, true),
            ('EGP', 'Egyptian Pound', 2, true),
            ('QAR', 'Qatari Riyal', 2, true),
            ('KWD', 'Kuwaiti Dinar', 3, true),
            ('BHD', 'Bahraini Dinar', 3, true),
            ('JOD', 'Jordanian Dinar', 3, true),
            ('OMR', 'Omani Rial', 3, true),
            ('TRY', 'Turkish Lira', 2, true),
            ('MAD', 'Moroccan Dirham', 2, true),
            ('JPY', 'Japanese Yen', 0, true)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO languages (code, name, direction, is_active) VALUES
            ('ar', 'Arabic', 'rtl', true),
            ('en', 'English', 'ltr', true),
            ('fr', 'French', 'ltr', true),
            ('tr', 'Turkish', 'ltr', true)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO ad_platforms (code, name, is_active) VALUES
            ('meta', 'Meta', true),
            ('tiktok', 'TikTok', true),
            ('google', 'Google', true),
            ('snapchat', 'Snapchat', true)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO event_types (code, description, is_active) VALUES
            ('page_view', 'Visitor loaded a landing page.', true),
            ('product_view', 'Visitor viewed a product.', true),
            ('cta_click', 'Visitor clicked a call-to-action.', true),
            ('whatsapp_click', 'Visitor clicked a WhatsApp contact link.', true),
            ('cod_form_start', 'Visitor started the cash-on-delivery order form.', true),
            ('cod_order_submitted', 'Visitor submitted the cash-on-delivery order form.', true),
            ('deposit_confirmed', 'A deposit was confirmed for an order.', true)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS event_types")
    op.execute("DROP TABLE IF EXISTS ad_platforms")
    op.execute("DROP TABLE IF EXISTS languages")
    op.execute("DROP TABLE IF EXISTS currencies")
    op.execute("DROP TABLE IF EXISTS countries")
