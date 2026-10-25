"""TDD RED-тест: TPC-H sf=1 должен существовать в raw_tpch с точными rowcount.

Пока `just seed` не выполнен — тест падает (RED). После генерации — зелёный.
Ожидаемые counts — канонические для TPC-H sf=1.
"""

from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[3]
WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"

EXPECTED = {
    "region": 5,
    "nation": 25,
    "supplier": 10_000,
    "customer": 150_000,
    "part": 200_000,
    "partsupp": 800_000,
    "orders": 1_500_000,
    "lineitem": 6_001_215,
}


@pytest.fixture(scope="module")
def con():
    if not WAREHOUSE.exists():
        pytest.fail(f"хранилище не сгенерировано: выполните `just seed` (ожидался {WAREHOUSE})")
    c = duckdb.connect(str(WAREHOUSE), read_only=True)
    yield c
    c.close()


@pytest.mark.parametrize("table,expected", sorted(EXPECTED.items()))
def test_raw_tpch_rowcount(con, table, expected):
    n = con.execute(f"SELECT COUNT(*) FROM raw_tpch.{table}").fetchone()[0]
    assert n == expected, f"raw_tpch.{table}: {n} != {expected}"


def test_version_pin(con):
    """Защитный тест: файл хранилища создан duckdb 1.4.4 из venv проекта."""
    v = con.execute("SELECT version()").fetchone()[0]
    assert v.startswith("v1.4.4"), f"версия duckdb файла/драйвера: {v}, ожидалась v1.4.4"
