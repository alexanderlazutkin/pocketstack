#!/usr/bin/env python3
"""Ф1: генератор скелетов Cube-моделей AW (docs/ssasmd-cube-migration.md §8).

One-shot: скелеты генерируются ОДИН РАЗ и дальше живут в git — регенерация
перезапишет ручную доводку Ф2+, поэтому по умолчанию отказывается писать
поверх существующих файлов (--force для осознанного перезапуска).

Источники (артефакты репо-источника mssql-server-samplesdb, док §5):
  --ddl  aw_dw2019_schema.sql — имена таблиц/колонок, типы, PRIMARY KEY;
  --tsv  aw_metadata.tsv      — RU/EN комментарии таблиц и колонок
                                (table, '-', en, ru) / (table, col, en, ru).

Выход: packages/cube/model/cubes/<cube_name>.cube.yml — скелеты с
title/description RU, размерностями всех колонок, primary_key из DDL.
Иерархии/joins/меры — ручная доводка (Ф2/Ф3).

Запуск: uv run --with pyyaml scripts/gen_aw_cube_models.py [--force]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# --- входы/выходы по умолчанию ------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
DDL_DEFAULT = Path(
    "~/Git/DB/sqlserver/mssql-server-samplesdb/migration/ddl/aw_dw2019_schema.sql"
).expanduser()
TSV_DEFAULT = Path(
    "~/Git/DB/sqlserver/mssql-server-samplesdb/migration/ddl/aw_metadata.tsv"
).expanduser()
OUT_DEFAULT = REPO / "packages" / "cube" / "model" / "cubes"

# Служебные/вне скоупа SSAS-куба (док §2): скелеты не генерируем.
SKIP_TABLES = {
    "AdventureWorksDWBuildVersion",
    "DatabaseLog",
    "ProspectiveBuyer",
    "NewFactCurrencyRate",  # пустой дубль курса в AW-датасете
    "FactAdditionalInternationalProductDescription",
}

# Семантические имена кубов фактов по конвенции §6 (не aw_fact_*).
FACT_CUBE_NAMES = {
    "FactInternetSales": "aw_internet_sales",
    "FactResellerSales": "aw_reseller_sales",
    "FactSalesQuota": "aw_sales_targets",
    "FactFinance": "aw_finance",
    "FactCurrencyRate": "aw_exchange_rates",
    "FactInternetSalesReason": "aw_sales_reason_bridge",
    "FactProductInventory": "aw_product_inventory",
    "FactCallCenter": "aw_call_center",
    "FactSurveyResponse": "aw_survey_response",
}

GENERATED_HEADER = (
    "# СКЕЛЕТ сгенерирован scripts/gen_aw_cube_models.py (Ф1). Ручная доводка Ф2+;\n"
    "# регенерация сотрёт её (--force). Конвенции: docs/ssasmd-cube-migration.md §6.\n"
)

# --- парсинг -------------------------------------------------------------------


def parse_ddl(text: str) -> dict[str, dict]:
    """DDL → {table: {columns: [(name, decltype, not_null)], pk: [cols]}}."""
    tables: dict[str, dict] = {}
    table_re = re.compile(r"CREATE TABLE IF NOT EXISTS dbo\.\"(\w+)\"\s*\((.*?)\n\);", re.DOTALL)
    col_re = re.compile(
        r"^\s+\"(\w+)\"\s+([A-Z]+(?:\(\d+(?:,\d+)?\))?)\s*(NOT NULL)?\s*,?$", re.MULTILINE
    )
    pk_re = re.compile(r"PRIMARY KEY \(([^)]+)\)")
    for m in table_re.finditer(text):
        table, body = m.group(1), m.group(2)
        columns = [(cm.group(1), cm.group(2), bool(cm.group(3))) for cm in col_re.finditer(body)]
        pk_m = pk_re.search(body)
        pk = [c.strip().strip('"') for c in pk_m.group(1).split(",")] if pk_m else []
        tables[table] = {"columns": columns, "pk": pk}
    return tables


def parse_metadata(text: str) -> dict[tuple[str, str | None], tuple[str, str]]:
    """TSV → {(table, col|None): (en, ru)}; col=None — строка таблицы."""
    meta: dict[tuple[str, str | None], tuple[str, str]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            raise ValueError(f"aw_metadata.tsv: ожидалось 4 поля, получено {len(parts)}: {line!r}")
        table, col, en, ru = parts
        meta[(table, None if col == "-" else col)] = (en, ru)
    return meta


# --- маппинг -------------------------------------------------------------------


def snake(camel: str) -> str:
    """PascalCase → snake_case: CustomerKey → customer_key, AddressLine1 → address_line1."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()


def cube_type(decltype: str) -> str:
    """SQL-тип DuckDB → тип размерности Cube."""
    t = decltype.upper()
    if t.startswith(
        (
            "DECIMAL",
            "NUMERIC",
            "BIGINT",
            "INTEGER",
            "SMALLINT",
            "TINYINT",
            "REAL",
            "DOUBLE",
            "FLOAT",
        )
    ):
        return "number"
    if t.startswith("BOOLEAN"):
        return "boolean"
    if t.startswith(("TIMESTAMP", "DATE", "TIME")):
        return "time"
    return "string"


def short_title(ru: str, fallback: str) -> str:
    """Короткий title из RU-комментария: до первого '.'/':'/' — '/' ('.'"""
    cut = re.split(r"[.:;—(]", ru, maxsplit=1)[0].strip(" ,")
    return cut[:60] if cut else fallback


def cube_name_for(table: str) -> str:
    if table.startswith("Dim"):
        return "aw_dim_" + snake(table.removeprefix("Dim"))
    if table in FACT_CUBE_NAMES:
        return FACT_CUBE_NAMES[table]
    return "aw_" + snake(table)


def build_cube(table: str, ddl: dict, meta: dict) -> dict:
    """Скелет куба: размеры всех колонок, PK из DDL, RU title/description."""
    en_t, ru_t = meta.get((table, None), ("", table))
    dims = []
    for col, decltype, _notnull in ddl["columns"]:
        en_c, ru_c = meta.get((table, col), ("", col))
        dim = {
            "name": snake(col),
            "title": short_title(ru_c, snake(col)),
            "sql": '{CUBE}."' + col + '"',
            "type": cube_type(decltype),
            "description": ru_c or en_c or col,
        }
        if col in ddl["pk"]:
            dim["primary_key"] = True
        dims.append(dim)

    return {
        "name": cube_name_for(table),
        "title": short_title(ru_t, table),
        "description": f"{ru_t or en_t}. Grain/единицы — см. док §2; {en_t}",
        "sql": 'SELECT * FROM aw_dw2019_ru.dbo."' + table + '"',
        "joins": [],
        "dimensions": dims,
    }


# --- генерация файлов ------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ddl", type=Path, default=DDL_DEFAULT)
    ap.add_argument("--tsv", type=Path, default=TSV_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--force", action="store_true", help="перезаписывать существующие файлы")
    args = ap.parse_args()

    import yaml  # uv run --with pyyaml

    tables = parse_ddl(args.ddl.read_text(encoding="utf-8"))
    meta = parse_metadata(args.tsv.read_text(encoding="utf-8"))

    written, skipped = [], []
    for table, ddl in sorted(tables.items()):
        if table in SKIP_TABLES:
            skipped.append(table)
            continue
        cube = build_cube(table, ddl, meta)
        path = args.out / f"{cube['name']}.cube.yml"
        if path.exists() and not args.force:
            print(f"SKIP (существует, без --force): {path.name}")
            continue
        body = yaml.dump(
            {"cubes": [cube]},
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=100,
        )
        path.write_text(GENERATED_HEADER + body, encoding="utf-8")
        written.append(path.name)

    print(f"\nготово: {len(written)} скелетов → {args.out}")
    print(f"пропущено таблиц (SKIP_TABLES): {len(skipped)}: {', '.join(sorted(skipped))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
