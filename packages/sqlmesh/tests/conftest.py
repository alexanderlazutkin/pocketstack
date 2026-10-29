"""Общие помощники тестов sqlmesh: sf-маркер хранилища и масштабируемые эталоны.

Маркер sf — таблица pocketstack_meta, пишется seed_tpch.py в обоих режимах
(WAREHOUSE_MODE=file|ducklake; процедура смены sf — docs/plan.md Stage 7).
Эталоны counts заданы для sf=1; при целом sf масштабируются линейно,
region/nation — константы dbgen (не масштабируются), дробный sf — skip.
"""

from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[3]
WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"

# Канонические counts TPC-H sf=1 (dbgen)
RAW_BASE = {
    "region": 5,
    "nation": 25,
    "supplier": 10_000,
    "customer": 150_000,
    "part": 200_000,
    "partsupp": 800_000,
    "orders": 1_500_000,
    "lineitem": 6_001_215,
}
RAW_CONSTANT = {"region", "nation"}  # не масштабируются от sf

MARTS_BASE = {
    "dim_customer": 150_000,
    "dim_supplier": 10_000,
    "dim_part": 200_000,
    "dim_order": 1_500_000,
    "fact_sales": 6_001_215,
}

# Счётчик lineitem у dbgen НЕ строго линеен от sf (порождается из orders с рандомизацией
# 1–7 строк на заказ): sf=1 → 6 001 215 ровно, но sf=10 → 59 986 052, а не 60 012 150.
# fact_sales наследует 1:1. Для них — относительный допуск 0.1%, остальные таблицы
# (и dim_*) линейны точно.
APPROX_REL = {"lineitem", "fact_sales"}
APPROX_TOL = 0.001


def assert_count(table: str, got: int, expected: int) -> None:
    """Точная сверка counts; для нелинейных от sf таблиц — допуск 0.1%."""
    if table in APPROX_REL:
        assert abs(got - expected) <= APPROX_TOL * expected, (
            f"{table}: {got} != ~{expected} (допуск 0.1%, нелинейность dbgen)"
        )
    else:
        assert got == expected, f"{table}: {got} != {expected}"


def warehouse_sf(con) -> float | None:
    """sf из маркера pocketstack_meta; None — маркера нет (хранилище до Stage 7)."""
    try:
        row = con.execute("SELECT value FROM pocketstack_meta WHERE key = 'sf'").fetchone()
        return float(row[0]) if row else None
    except duckdb.Error:
        return None


def require_int_sf(con) -> int:
    """Целый sf из маркера; нет маркера — fail (явно), дробный — skip."""
    sf = warehouse_sf(con)
    if sf is None:
        pytest.fail(
            "нет маркера sf (pocketstack_meta) — пересоздайте хранилище: "
            "`just seed` / `scripts/stack.sh rebuild [SF]` (docs/plan.md Stage 7)"
        )
    if not sf.is_integer():
        pytest.skip(f"дробный sf={sf}: эталонные counts нелинейны")
    return int(sf)


def scaled(base: dict, sf: int, constant: frozenset | set = frozenset()) -> dict:
    return {t: (n if t in constant else n * sf) for t, n in base.items()}
