"""Генерация TPC-H sf=N в схему raw_tpch хранилища.

Режимы (WAREHOUSE_MODE, см. .env.example и docs/plan.md Stage 7):
- file (основной, default): dbgen прямо в warehouse/pocketstack.duckdb;
- ducklake (опция): dbgen во ВРЕМЕННЫЙ локальный файл → CTAS в lake.raw_tpch
  ОДНОЙ транзакцией каталога (pg + MinIO); снапшот-изоляция: старые данные
  живут в time-travel до prune (процедура «Смена sf» в plan.md).

Маркер sf — таблица pocketstack_meta в обоих режимах; тесты масштабируют
эталоны по нему (целые sf), region/nation — константы dbgen.

Запуск: uv run python packages/sqlmesh/seed_tpch.py [sf]
Системный DuckDB CLI 2.0 к файлам проекта — только через `just cli-readonly`.
"""

import os
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"
TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"Не задана переменная {name} — нужна для WAREHOUSE_MODE=ducklake "
            "(скопируйте .env.example → .env, раздел DuckLake; docs/plan.md Stage 7)"
        )
    return value


def _dbgen(con: duckdb.DuckDBPyConnection, sf: float) -> None:
    con.execute("INSTALL tpch")
    con.execute("LOAD tpch")
    con.execute(f"CALL dbgen(sf={sf})")


def _write_meta(con: duckdb.DuckDBPyConnection, sf: float, prefix: str = "") -> None:
    # без PRIMARY KEY: ducklake не поддерживает PK/UNIQUE-констрейнты;
    # уникальность ключа обеспечивает DELETE+INSERT
    con.execute(f"CREATE TABLE IF NOT EXISTS {prefix}pocketstack_meta (key VARCHAR, value VARCHAR)")
    con.execute(f"DELETE FROM {prefix}pocketstack_meta WHERE key = 'sf'")
    con.execute(f"INSERT INTO {prefix}pocketstack_meta VALUES ('sf', '{sf}')")


def _report(con: duckdb.DuckDBPyConnection, lake: bool) -> None:
    prefix = "lake." if lake else ""
    for t in TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {prefix}raw_tpch.{t}").fetchone()[0]
        print(f"{prefix}raw_tpch.{t}: {n}")


def seed_file(sf: float) -> None:
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    try:
        con.execute("DROP SCHEMA IF EXISTS raw_tpch CASCADE")
        for t in TABLES:
            con.execute(f"DROP TABLE IF EXISTS main.{t}")
        _dbgen(con, sf)
        con.execute("CREATE SCHEMA raw_tpch")
        for t in TABLES:
            con.execute(f"CREATE TABLE raw_tpch.{t} AS SELECT * FROM main.{t}")
            con.execute(f"DROP TABLE main.{t}")
        _write_meta(con, sf)
        _report(con, lake=False)
        con.execute("CHECKPOINT")
    finally:
        con.close()


def lake_attach(
    con: duckdb.DuckDBPyConnection, read_only: bool = False, alias: str = "lake"
) -> None:
    """ATTACH ducklake-каталога (pg) + S3-настройки сессии (MinIO).

    read_only=True — для читателей (Cube, harness): защита от случайной
    AUTOMATIC_MIGRATION каталога. alias='pocketstack' — логическое имя хранилища
    (так каталог виден в семантической модели Cube и референсном SQL harness).
    """
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")
    for s in (
        f"SET s3_endpoint='{_required_env('DUCKLAKE_S3_ENDPOINT')}'",
        "SET s3_use_ssl=false",
        "SET s3_url_style='path'",
        f"SET s3_access_key_id='{_required_env('DUCKLAKE_S3_ACCESS_KEY')}'",
        f"SET s3_secret_access_key='{_required_env('DUCKLAKE_S3_SECRET_KEY')}'",
    ):
        con.execute(s)
    dsn = (
        f"postgres:dbname={_required_env('DUCKLAKE_PG_DB')} "
        f"user={_required_env('DUCKLAKE_PG_USER')} "
        f"password={_required_env('DUCKLAKE_PG_PASSWORD')} "
        f"host={_required_env('DUCKLAKE_PG_HOST')} port={_required_env('DUCKLAKE_PG_PORT')}"
    )
    data_path = f"s3://{_required_env('DUCKLAKE_S3_BUCKET')}/"
    ro = ", READ_ONLY" if read_only else ""
    con.execute(f"ATTACH '{dsn}' AS {alias} (TYPE ducklake, DATA_PATH '{data_path}'{ro})")


def seed_ducklake(sf: float) -> None:
    """dbgen локально → атомарный перенос в lake.raw_tpch одной транзакцией каталога."""
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    tmp = WAREHOUSE.parent / f".seed_tmp_{os.getpid()}.duckdb"
    tmp.unlink(missing_ok=True)
    try:
        src = duckdb.connect(str(tmp))
        try:
            _dbgen(src, sf)
        finally:
            src.close()

        con = duckdb.connect()
        try:
            lake_attach(con)
            con.execute(f"ATTACH '{tmp}' AS src (READ_ONLY)")
            con.execute("BEGIN")
            con.execute("DROP SCHEMA IF EXISTS lake.raw_tpch CASCADE")
            con.execute("CREATE SCHEMA lake.raw_tpch")
            for t in TABLES:
                con.execute(f"CREATE TABLE lake.raw_tpch.{t} AS SELECT * FROM src.main.{t}")
            _write_meta(con, sf, prefix="lake.")
            con.execute("COMMIT")
            _report(con, lake=True)
        finally:
            con.close()
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    sf = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    mode = os.environ.get("WAREHOUSE_MODE", "file")
    if mode == "ducklake":
        seed_ducklake(sf)
    elif mode == "file":
        seed_file(sf)
    else:
        raise SystemExit(f"Неизвестный WAREHOUSE_MODE={mode} (допустимо file|ducklake)")


if __name__ == "__main__":
    main()
