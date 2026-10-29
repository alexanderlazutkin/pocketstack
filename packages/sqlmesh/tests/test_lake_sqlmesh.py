"""TDD интеграционный тест ducklake-режима sqlmesh (Stage 7, шаг 4).

Опциональный: RUN_LAKE_TESTS=1 при поднятом ducklake-стеке (docker compose up -d --wait).
Цикл: seed lake sf=1 → `sqlmesh plan --gateway lake --auto-apply` → звезда в lake.marts;
повторный plan — идемпотентен (изменений нет, counts стабильны).
"""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # packages/sqlmesh → seed_tpch

from conftest import MARTS_BASE, assert_count

SQLMESH_DIR = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LAKE_TESTS") != "1",
    reason="RUN_LAKE_TESTS!=1 — нужен ducklake-стек (docker compose up -d --wait)",
)


def _sqlmesh_plan_lake() -> str:
    proc = subprocess.run(
        ["uv", "run", "sqlmesh", "--gateway", "lake", "plan", "--auto-apply", "--no-prompts"],
        cwd=SQLMESH_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"sqlmesh plan упал:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    return proc.stdout


def test_sqlmesh_lake_build_and_idempotency():
    import seed_tpch

    seed_tpch.seed_ducklake(1.0)
    _sqlmesh_plan_lake()
    out2 = _sqlmesh_plan_lake()

    con = duckdb.connect()
    try:
        seed_tpch.lake_attach(con)
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_catalog = 'lake' AND table_schema = 'marts'"
            ).fetchall()
        }
        for table, base in MARTS_BASE.items():  # sf=1
            assert table in tables, f"lake.marts.{table} не построена"
            n = con.execute(f"SELECT COUNT(*) FROM lake.marts.{table}").fetchone()[0]
            assert_count(table, n, base)
    finally:
        con.close()

    # Идемпотентность: повторный план не перестраивает витрину
    low2 = out2.lower()
    assert "no changes" in low2 or "nothing to" in low2, (
        f"повторный plan не распознан как no-op:\n{out2[:1500]}"
    )
