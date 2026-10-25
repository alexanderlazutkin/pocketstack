"""Генерация TPC-H sf=N в схему raw_tpch хранилища.

Запуск: uv run python packages/sqlmesh/seed_tpch.py [sf]
Системный DuckDB CLI 2.0 к этому файлу — только через `just cli-readonly`.
"""

import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"
TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]


def _drop_existing(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DROP SCHEMA IF EXISTS raw_tpch CASCADE")
    for t in TABLES:
        con.execute(f"DROP TABLE IF EXISTS main.{t}")


def _move_to_raw(con: duckdb.DuckDBPyConnection) -> None:
    """dbgen создаёт таблицы в main независимо от search_path — переносим CTAS."""
    con.execute("CREATE SCHEMA raw_tpch")
    for t in TABLES:
        con.execute(f"CREATE TABLE raw_tpch.{t} AS SELECT * FROM main.{t}")
        con.execute(f"DROP TABLE main.{t}")


def main() -> None:
    sf = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    try:
        con.execute("INSTALL tpch")
        con.execute("LOAD tpch")
        _drop_existing(con)
        con.execute(f"CALL dbgen(sf={sf})")
        _move_to_raw(con)
        for t in TABLES:
            n = con.execute(f"SELECT COUNT(*) FROM raw_tpch.{t}").fetchone()[0]
            print(f"raw_tpch.{t}: {n}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
