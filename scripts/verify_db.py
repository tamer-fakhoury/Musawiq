"""Local verification pipeline (replaces a CI host).

Creates a uniquely named scratch database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
then runs:

    alembic upgrade head  ->  schema parity  ->  pytest  ->  alembic downgrade base

and finally drops the scratch database. Any failure returns a non-zero exit
code. The database is always dropped unless ``--keep`` is passed.

Usage:
    python -m scripts.verify_db
    python -m scripts.verify_db --expect-rls
    python -m scripts.verify_db --keep --no-down
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def run_step(label: str, args: list[str], env: dict[str, str]) -> None:
    print(f"\n=== {label} ===")
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the database from empty.")
    parser.add_argument("--keep", action="store_true", help="keep the scratch database")
    parser.add_argument("--no-down", action="store_true", help="skip downgrade base")
    parser.add_argument("--expect-rls", action="store_true", help="assert RLS is enabled")
    args = parser.parse_args(argv)

    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    app_url = os.getenv("MUSAWIQ_DATABASE_URL")
    if not admin_url:
        print("FAIL: MUSAWIQ_ADMIN_DATABASE_URL is not set", file=sys.stderr)
        return 1
    if not app_url:
        print("FAIL: MUSAWIQ_DATABASE_URL is not set", file=sys.stderr)
        return 1

    scratch = f"musawiq_verify_{uuid.uuid4().hex[:10]}"
    scratch_url = with_database(app_url, scratch)

    env = os.environ.copy()
    env["MUSAWIQ_DATABASE_URL"] = scratch_url
    env["MUSAWIQ_TEST_DATABASE_URL"] = scratch_url
    env.pop("MUSAWIQ_EXPECT_RLS", None)
    if args.expect_rls:
        env["MUSAWIQ_EXPECT_RLS"] = "1"

    admin = psycopg.connect(libpq_url(admin_url), autocommit=True)
    try:
        app_user = urlsplit(app_url).username
        with admin.cursor() as cur:
            if app_user:
                try:
                    cur.execute(
                        f"CREATE DATABASE {quote_ident(scratch)} "
                        f"OWNER {quote_ident(app_user)}"
                    )
                except psycopg.errors.UndefinedObject:
                    print(
                        f"FAIL: database role {app_user!r} does not exist; "
                        "create it or fix MUSAWIQ_DATABASE_URL",
                        file=sys.stderr,
                    )
                    return 1
            else:
                cur.execute(f"CREATE DATABASE {quote_ident(scratch)}")
        print(f"created scratch database: {scratch} (owner: {app_user or 'admin'})")

        try:
            run_step(
                "alembic upgrade head",
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env,
            )
            run_step(
                "schema parity",
                [sys.executable, "-m", "scripts.parity_check"],
                env,
            )
            run_step(
                "pytest tests/db",
                [sys.executable, "-m", "pytest", "tests/db", "-q"],
                env,
            )

            if not args.no_down:
                run_step(
                    "alembic downgrade base",
                    [sys.executable, "-m", "alembic", "downgrade", "base"],
                    env,
                )
                run_step(
                    "post-downgrade emptiness",
                    [sys.executable, "-m", "scripts.verify_db", "--check-empty"],
                    env,
                )
        finally:
            if args.keep:
                print(f"\nkept scratch database: {scratch}")
            else:
                with admin.cursor() as cur:
                    cur.execute(f"DROP DATABASE IF EXISTS {quote_ident(scratch)} WITH (FORCE)")
                print(f"dropped scratch database: {scratch}")

    finally:
        admin.close()

    print("\nVERIFY OK")
    return 0


def check_empty() -> int:
    """Assert no public tables remain after downgrade (tool tables excluded)."""
    url = os.getenv("MUSAWIQ_TEST_DATABASE_URL")
    if not url:
        print("FAIL: MUSAWIQ_TEST_DATABASE_URL is not set", file=sys.stderr)
        return 1
    with psycopg.connect(libpq_url(url)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        remaining = [r[0] for r in cur.fetchall()]
    leftover = [t for t in remaining if t not in {"schema_migrations", "alembic_version"}]
    if leftover:
        print(f"FAIL: tables remain after downgrade: {leftover}", file=sys.stderr)
        return 1
    print("EMPTY OK")
    return 0


if __name__ == "__main__":
    if "--check-empty" in sys.argv:
        raise SystemExit(check_empty())
    raise SystemExit(main())
