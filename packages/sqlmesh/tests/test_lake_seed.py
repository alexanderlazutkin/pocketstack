"""TDD интеграционный тест ducklake-режима seed (Stage 7, шаг 3).

Опциональный (медленный, нужна инфраструктура): запускать с RUN_LAKE_TESTS=1
при поднятом ducklake-стеке (docker compose up -d --wait).
Сеет sf=1 в lake.raw_tpch (data-path s3://bucket/warehouse/), сверяет counts,
маркер sf и идемпотентность повторного запуска (DROP+CREATE одной транзакцией).
"""

import os
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # packages/sqlmesh → seed_tpch

from conftest import RAW_BASE, assert_count

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LAKE_TESTS") != "1",
    reason="RUN_LAKE_TESTS!=1 — нужен ducklake-стек (docker compose up -d --wait)",
)


def test_seed_ducklake_sf1_idempotent():
    import seed_tpch

    seed_tpch.seed_ducklake(1.0)
    seed_tpch.seed_ducklake(1.0)  # повторный запуск: итоговое состояние то же

    con = duckdb.connect()
    try:
        seed_tpch.lake_attach(con)
        sf = con.execute("SELECT value FROM lake.pocketstack_meta WHERE key = 'sf'").fetchone()
        assert sf is not None, "маркер sf в lake.pocketstack_meta не записан"
        assert float(sf[0]) == 1.0
        for table, base in RAW_BASE.items():  # sf=1 → expected = base
            n = con.execute(f"SELECT COUNT(*) FROM lake.raw_tpch.{table}").fetchone()[0]
            assert_count(table, n, base)
    finally:
        con.close()
