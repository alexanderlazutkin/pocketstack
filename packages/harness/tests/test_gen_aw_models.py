"""Юнит-тесты генератора скелетов AW-моделей (Ф1, docs/ssasmd-cube-migration.md §8).

Генератор one-shot: скелеты создаются один раз и дальше живут в git.
Здесь проверяем чистые функции парсинга/маппинга без обращения к БД.
"""

import importlib.util
from pathlib import Path

import pytest

# scripts/ — не пакет; грузим по пути
_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "gen_aw_cube_models.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_aw_cube_models", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_module()


DDL_SNIPPET = """
CREATE SCHEMA IF NOT EXISTS dbo;

CREATE TABLE IF NOT EXISTS dbo."DimCurrency" (
    "CurrencyKey" INTEGER NOT NULL,
    "CurrencyAlternateKey" VARCHAR(3) NOT NULL,
    "CurrencyName" VARCHAR NOT NULL,
    PRIMARY KEY ("CurrencyKey")
);

CREATE TABLE IF NOT EXISTS dbo."FactInternetSales" (
    "ProductKey" INTEGER NOT NULL,
    "OrderDate" TIMESTAMP,
    "UnitPrice" DECIMAL(19,4) NOT NULL,
    "UnitPriceDiscountPct" DOUBLE NOT NULL,
    "SalesAmount" DECIMAL(19,4) NOT NULL,
    "CarrierTrackingNumber" VARCHAR,
    PRIMARY KEY ("ProductKey", "OrderDate")
);
"""

TSV_SNIPPET = (
    "DimCurrency\t-\tCurrency dimension\tИзмерение валют\n"
    "DimCurrency\tCurrencyKey\tSurrogate primary key of the currency\t"
    "Суррогатный первичный ключ валюты\n"
    "DimCurrency\tCurrencyName\tCurrency name\tНазвание валюты ( англ. )\n"
    "FactInternetSales\t-\tInternet sales fact\tФакт интернет-продаж: строка заказа\n"
)


class TestParseDdl:
    def test_tables_and_columns(self, gen):
        tables = gen.parse_ddl(DDL_SNIPPET)
        assert set(tables) == {"DimCurrency", "FactInternetSales"}
        cur = tables["DimCurrency"]
        assert cur["columns"][0] == ("CurrencyKey", "INTEGER", True)
        assert cur["columns"][2] == ("CurrencyName", "VARCHAR", True)
        # VARCHAR(3) с длиной
        assert cur["columns"][1] == ("CurrencyAlternateKey", "VARCHAR(3)", True)

    def test_primary_key_single_and_composite(self, gen):
        tables = gen.parse_ddl(DDL_SNIPPET)
        assert tables["DimCurrency"]["pk"] == ["CurrencyKey"]
        assert tables["FactInternetSales"]["pk"] == ["ProductKey", "OrderDate"]


class TestParseMetadata:
    def test_table_and_column_rows(self, gen):
        meta = gen.parse_metadata(TSV_SNIPPET)
        assert meta[("DimCurrency", None)] == ("Currency dimension", "Измерение валют")
        assert meta[("DimCurrency", "CurrencyKey")] == (
            "Surrogate primary key of the currency",
            "Суррогатный первичный ключ валюты",
        )
        assert meta[("FactInternetSales", None)][1].startswith("Факт интернет")


class TestMapping:
    @pytest.mark.parametrize(
        ("decltype", "expected"),
        [
            ("INTEGER", "number"),
            ("BIGINT", "number"),
            ("DECIMAL(19,4)", "number"),
            ("DOUBLE", "number"),
            ("VARCHAR", "string"),
            ("VARCHAR(3)", "string"),
            ("BOOLEAN", "boolean"),
            ("DATE", "time"),
            ("TIMESTAMP", "time"),
        ],
    )
    def test_cube_type(self, gen, decltype, expected):
        assert gen.cube_type(decltype) == expected

    @pytest.mark.parametrize(
        ("camel", "snake"),
        [
            ("CurrencyKey", "currency_key"),
            ("UnitPriceDiscountPct", "unit_price_discount_pct"),
            ("AddressLine1", "address_line1"),
            ("SalesOrderNumber", "sales_order_number"),
            ("AccountKey", "account_key"),
        ],
    )
    def test_snake(self, gen, camel, snake):
        assert gen.snake(camel) == snake


class TestBuildCube:
    def test_dim_skeleton(self, gen):
        tables = gen.parse_ddl(DDL_SNIPPET)
        meta = gen.parse_metadata(TSV_SNIPPET)
        cube = gen.build_cube("DimCurrency", tables["DimCurrency"], meta)

        assert cube["name"] == "aw_dim_currency"
        assert cube["title"] == "Измерение валют"
        assert cube["sql"] == 'SELECT * FROM aw_dw2019_ru.dbo."DimCurrency"'
        assert cube["joins"] == []

        dims = {d["name"]: d for d in cube["dimensions"]}
        assert dims["currency_key"]["primary_key"] is True
        assert dims["currency_name"].get("primary_key", False) is False
        assert dims["currency_key"]["type"] == "number"
        assert dims["currency_name"]["type"] == "string"
        # sql размерности ссылается на РЕАЛЬНУЮ колонку PascalCase
        assert dims["currency_key"]["sql"] == '{CUBE}."CurrencyKey"'
        # RU-описание прокинуто
        assert "Суррогатный первичный ключ" in dims["currency_key"]["description"]

    def test_fact_cube_name_mapping(self, gen):
        tables = gen.parse_ddl(DDL_SNIPPET)
        meta = gen.parse_metadata(TSV_SNIPPET)
        cube = gen.build_cube("FactInternetSales", tables["FactInternetSales"], meta)
        # семантическое имя куба по плану §6, не aw_fact_*
        assert cube["name"] == "aw_internet_sales"

    def test_composite_pk_marks_all(self, gen):
        tables = gen.parse_ddl(DDL_SNIPPET)
        meta = gen.parse_metadata(TSV_SNIPPET)
        cube = gen.build_cube("FactInternetSales", tables["FactInternetSales"], meta)
        pk = [d["name"] for d in cube["dimensions"] if d.get("primary_key")]
        assert pk == ["product_key", "order_date"]

    def test_skip_tables(self, gen):
        assert "DatabaseLog" in gen.SKIP_TABLES
        assert "NewFactCurrencyRate" in gen.SKIP_TABLES
        assert "DimCustomer" not in gen.SKIP_TABLES
