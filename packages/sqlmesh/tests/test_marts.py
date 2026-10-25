"""TDD: звезда marts.* собрана из raw_tpch по контракту dbt-моделей пользователя (automate-dv-tpch).

Пока `just apply` (sqlmesh) не выполнен — схема marts отсутствует, тесты RED.
Контракты колонок и rowcount'ы соответствуют канону TPC-H sf=1 и models/marts исходного репо.
"""

from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[3]
WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"

EXPECTED_COUNTS = {
    "dim_customer": 150_000,
    "dim_supplier": 10_000,
    "dim_part": 200_000,
    "dim_order": 1_500_000,
    "fact_sales": 6_001_215,
}

CONTRACT = {
    "dim_customer": {
        "customer_id",
        "customer_key",
        "customer_name",
        "customer_addr",
        "customer_nation",
        "customer_region",
        "customer_phone",
        "customer_acct_balance",
        "market_segment",
    },
    "dim_supplier": {
        "supplier_id",
        "supplier_key",
        "supplier_name",
        "supplier_addr",
        "supplier_nation",
        "supplier_region",
        "supplier_phone",
        "supplier_acct_balance",
    },
    "dim_part": {
        "part_id",
        "part_key",
        "part_name",
        "manufacturer",
        "brand",
        "part_type",
        "part_size",
        "part_container",
        "part_retail_price",
    },
    "dim_order": {
        "order_id",
        "order_key",
        "order_status",
        "total_price",
        "order_date",
        "order_priority",
        "clerk",
        "ship_priority",
    },
    "fact_sales": {
        "order_id",
        "customer_id",
        "part_id",
        "supplier_id",
        "line_number",
        "quantity",
        "extended_price",
        "discount",
        "tax",
        "return_flag",
        "line_status",
        "ship_date",
        "commit_date",
        "receipt_date",
        "ship_instruct",
        "ship_mode",
        "comment",
        "net_price",
        "total_price_with_tax",
    },
}

FK = [
    ("fact_sales", "customer_id", "dim_customer", "customer_id"),
    ("fact_sales", "supplier_id", "dim_supplier", "supplier_id"),
    ("fact_sales", "part_id", "dim_part", "part_id"),
    ("fact_sales", "order_id", "dim_order", "order_id"),
]


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(WAREHOUSE), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def marts(con):
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        ).fetchall()
    }
    if not tables:
        pytest.fail("схема marts не собрана: выполните `just apply`")
    return tables


@pytest.mark.parametrize("table,expected", sorted(EXPECTED_COUNTS.items()))
def test_rowcount(con, marts, table, expected):
    assert table in marts, f"marts.{table} отсутствует"
    n = con.execute(f"SELECT COUNT(*) FROM marts.{table}").fetchone()[0]
    assert n == expected, f"marts.{table}: {n} != {expected}"


@pytest.mark.parametrize("table,columns", sorted(CONTRACT.items()))
def test_column_contract(con, table, columns):
    got = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = 'marts' AND table_name = '{table}'"
        ).fetchall()
    }
    assert got == columns, f"{table}: лишние={got - columns}, отсутствуют={columns - got}"


@pytest.mark.parametrize(
    "dim,idcol",
    [
        ("dim_customer", "customer_id"),
        ("dim_supplier", "supplier_id"),
        ("dim_part", "part_id"),
        ("dim_order", "order_id"),
    ],
)
def test_pk_unique(con, dim, idcol):
    dup = con.execute(
        f"SELECT COUNT(*) FROM (SELECT {idcol} FROM marts.{dim} GROUP BY 1 HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    assert dup == 0, f"marts.{dim}.{idcol}: {dup} дубликатов"


def test_fact_grain_unique(con):
    dup = con.execute(
        "SELECT COUNT(*) FROM (SELECT order_id, line_number FROM marts.fact_sales "
        "GROUP BY 1, 2 HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    assert dup == 0, f"grain факта (order_id, line_number): {dup} дубликатов"


@pytest.mark.parametrize("ft,fc,dt,dc", FK)
def test_fk_integrity(con, ft, fc, dt, dc):
    orphans = con.execute(
        f"SELECT COUNT(*) FROM marts.{ft} f LEFT JOIN marts.{dt} d ON d.{dc} = f.{fc} "
        f"WHERE d.{dc} IS NULL"
    ).fetchone()[0]
    assert orphans == 0, f"{ft}.{fc}: {orphans} сирот относительно {dt}"


def test_parity_raw_vs_fact(con):
    """Ключевая инварианта демо: витрина = raw без потерь и искажений мер."""
    raw = con.execute(
        "SELECT COUNT(*), SUM(l_extendedprice * (1 - l_discount)), "
        "SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) FROM raw_tpch.lineitem"
    ).fetchone()
    mart = con.execute(
        "SELECT COUNT(*), SUM(net_price), SUM(total_price_with_tax) FROM marts.fact_sales"
    ).fetchone()
    assert raw[0] == mart[0], f"rows: raw={raw[0]} mart={mart[0]}"
    assert raw[1] == mart[1], f"net_price: raw={raw[1]} mart={mart[1]}"
    assert raw[2] == mart[2], f"total_price_with_tax: raw={raw[2]} mart={mart[2]}"
