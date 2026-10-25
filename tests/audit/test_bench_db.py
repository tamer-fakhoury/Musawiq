from __future__ import annotations

from scripts import bench_db


def test_bench_small_runs_query_set(capsys) -> None:
    result = bench_db.main(
        ["--scratch", "--scale", "small", "--runs", "1"]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "Performance Baseline" in output
    assert "products_by_store_status" in output
    assert "orders_by_store_placed_at" in output
    assert "order_by_store_dedupe_hash" in output
    assert "import_history_by_store" in output
    assert "Overall: PASS" in output
