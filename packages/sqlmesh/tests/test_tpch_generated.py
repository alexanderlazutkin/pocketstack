"""TDD-тест: TPC-H raw_tpch существует с точными rowcount для ТЕКУЩЕГО sf.

Пока `just seed`/`rebuild` не выполнен — тест падает (RED). Ожидаемые counts —
канон TPC-H sf=1, масштабируются по маркеру pocketstack_meta (целые sf);
region/nation — константы dbgen; дробный sf — skip (см. tests/conftest.py).
"""

import duckdb
import pytest
from conftest import RAW_BASE, RAW_CONSTANT, WAREHOUSE, assert_count, require_int_sf, scaled


@pytest.fixture(scope="module")
def con():
    if not WAREHOUSE.exists():
        pytest.fail(f"хранилище не сгенерировано: выполните `just seed` (ожидался {WAREHOUSE})")
    c = duckdb.connect(str(WAREHOUSE), read_only=True)
    yield c
    c.close()


@pytest.mark.parametrize("table", sorted(RAW_BASE))
def test_raw_tpch_rowcount(con, table):
    expected = scaled(RAW_BASE, require_int_sf(con), RAW_CONSTANT)[table]
    n = con.execute(f"SELECT COUNT(*) FROM raw_tpch.{table}").fetchone()[0]
    assert_count(table, n, expected)


def test_version_pin(con):
    """Защитный тест: движок duckdb в venv = 1.5.5, выравнан с node-драйвером Cube
    (@duckdb/node-api 1.5.5) — обязательное условие общего ducklake-каталога
    (версии каталога 0.3 у 1.4.4 и 1.0 у 1.5.x несовместимы; см. docs/plan.md Stage 6)."""
    v = con.execute("SELECT version()").fetchone()[0]
    assert v.startswith("v1.5.5"), f"версия duckdb файла/драйвера: {v}, ожидалась v1.5.5"
