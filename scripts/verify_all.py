"""One-command verification for the Musawiq repository.

Runs, in order:
  1. migrations from empty -> down -> up, parity, DB tests   (hard)
  2. tool tests: tests/tools and tests/audit                (hard)
  3. schema documentation drift check                       (hard)
  4. foreign-key matrix drift check                         (hard)
  5. schema audit report                                    (soft: prints, never fails)

Exit code 0 only when every hard step passes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def run(label: str, args: list[str], hard: bool = True) -> bool:
    print(f"\n=== {label} ===")
    result = subprocess.run(args, cwd=ROOT, env=os.environ.copy())
    ok = result.returncode == 0
    if not ok and hard:
        print(f"FAILED: {label}")
    elif not ok:
        print(f"WARN (soft): {label}")
    return ok


def main() -> int:
    py = sys.executable
    hard_results: list[tuple[str, bool]] = []

    hard_results.append(
        (
            "verify_db",
            run("verify_db", [py, "-m", "scripts.verify_db", "--expect-rls"]),
        )
    )
    # tests/db run inside verify_db, against its migrated scratch database.
    # Tool/audit tests provision their own scratch databases.
    hard_results.append(
        (
            "pytest tests/tools tests/audit",
            run(
                "pytest",
                [py, "-m", "pytest", "tests/tools", "tests/audit", "-q"],
            ),
        )
    )
    hard_results.append(
        (
            "schema docs drift",
            run("gen_schema_docs --check", [py, "-m", "scripts.gen_schema_docs", "--check"]),
        )
    )
    hard_results.append(
        (
            "fk matrix drift",
            run("fk_matrix --check", [py, "-m", "scripts.fk_matrix", "--check"]),
        )
    )

    run("schema audit (soft)", [py, "-m", "scripts.audit_schema", "--scratch"], hard=False)

    failed = [name for name, ok in hard_results if not ok]
    print("\n" + "=" * 60)
    if failed:
        print("VERIFY ALL FAILED: " + ", ".join(failed))
        return 1
    print("VERIFY ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
