"""Golden-тесты миграции AW SSAS→Cube (Ф9, docs/ssasmd-cube-migration.md §9).

Паритет: Cube REST (:4000, dev-режим) == прямой SQL к aw_dw2019_ru.duckdb
(read-only, движок тестовой среды). Эталоны зафиксированы в док-миграции:
Internet 29 358 677.2207 / Reseller 80 450 596.9823 / Finance 1 358 640 412.70.
Плюс анти-фан-аут (M2M/снежинки), унарная эмуляция (баланс = 0), консистентность
производных кубов (mov/KPI/flatten).
"""

from pathlib import Path

import duckdb
import pytest
import requests
from conftest import CUBE_URL_VALUE

REPO = Path(__file__).resolve().parents[3]
AW_DB = REPO / "warehouse" / "aw_dw2019_ru.duckdb"

TOL = 0.01  # цент: суммы DECIMAL(19,4) против float REST

ETALON_INTERNET = 29358677.2207
ETALON_RESELLER = 80450596.9823
ETALON_FINANCE = 1358640412.70


@pytest.fixture(scope="session")
def aw():
    if not AW_DB.exists():
        pytest.skip(f"нет {AW_DB} — восстановите (docs/ssasmd-cube-migration.md §5)")
    con = duckdb.connect()
    con.execute(f"ATTACH '{AW_DB}' AS aw (READ_ONLY)")
    return con


@pytest.fixture(scope="session")
def rest(cube_up):
    def _load(query):
        r = requests.post(
            f"{CUBE_URL_VALUE}/cubejs-api/v1/load",
            json={"query": query},
            timeout=120,
        )
        assert r.status_code == 200, f"/load {r.status_code}: {r.text[:300]}"
        return r.json()["data"]

    return _load


def _m(rows, member):
    assert rows, f"пустой ответ для {member}"
    return float(rows[0][member])


class TestBaseTotals:
    def test_internet_total(self, aw, rest):
        sql = _m(
            rest({"measures": ["aw_internet_sales.sales_amount"]}), "aw_internet_sales.sales_amount"
        )
        ref = float(
            aw.execute('SELECT SUM("SalesAmount") FROM aw.dbo."FactInternetSales"').fetchone()[0]
        )
        assert sql == pytest.approx(ref, abs=TOL)
        assert sql == pytest.approx(ETALON_INTERNET, abs=TOL)

    def test_reseller_total(self, aw, rest):
        sql = _m(
            rest({"measures": ["aw_reseller_sales.sales_amount"]}), "aw_reseller_sales.sales_amount"
        )
        ref = float(
            aw.execute('SELECT SUM("SalesAmount") FROM aw.dbo."FactResellerSales"').fetchone()[0]
        )
        assert sql == pytest.approx(ref, abs=TOL)
        assert sql == pytest.approx(ETALON_RESELLER, abs=TOL)

    def test_summary_equals_sum_of_channels(self, rest):
        rows = rest(
            {
                "measures": ["aw_sales_summary.sales_amount"],
                "dimensions": ["aw_sales_summary.sales_channel"],
            }
        )
        total = sum(float(r["aw_sales_summary.sales_amount"]) for r in rows)
        assert total == pytest.approx(ETALON_INTERNET + ETALON_RESELLER, abs=TOL)

    def test_distinct_counts_internet(self, aw, rest):
        rows = rest(
            {"measures": ["aw_internet_sales.order_count", "aw_internet_sales.customer_count"]}
        )
        ref_orders, ref_customers = aw.execute(
            'SELECT COUNT(DISTINCT "SalesOrderNumber"), COUNT(DISTINCT "CustomerKey") '
            'FROM aw.dbo."FactInternetSales"'
        ).fetchone()
        assert _m(rows, "aw_internet_sales.order_count") == float(ref_orders)
        assert _m(rows, "aw_internet_sales.customer_count") == float(ref_customers)

    def test_quota_total(self, aw, rest):
        sql = _m(
            rest({"measures": ["aw_sales_targets.sales_amount_quota"]}),
            "aw_sales_targets.sales_amount_quota",
        )
        ref = aw.execute('SELECT SUM("SalesAmountQuota") FROM aw.dbo."FactSalesQuota"').fetchone()[
            0
        ]
        assert sql == pytest.approx(ref, abs=TOL)


class TestFanout:
    """Join-деревья и мосты не должны размножать суммы (§9)."""

    def test_internet_by_category_no_fanout(self, rest):
        rows = rest(
            {
                "measures": ["aw_internet_sales.sales_amount"],
                "dimensions": ["aw_dim_product.category_name"],
            }
        )
        total = sum(float(r["aw_internet_sales.sales_amount"]) for r in rows)
        assert total == pytest.approx(ETALON_INTERNET, abs=TOL)

    def test_reseller_by_country_no_fanout(self, rest):
        rows = rest(
            {
                "measures": ["aw_reseller_sales.sales_amount"],
                "dimensions": ["aw_dim_reseller.country"],
            }
        )
        total = sum(float(r["aw_reseller_sales.sales_amount"]) for r in rows)
        assert total == pytest.approx(ETALON_RESELLER, abs=TOL)

    def test_internet_by_order_year_no_fanout(self, rest):
        rows = rest(
            {
                "measures": ["aw_internet_sales.sales_amount"],
                "dimensions": ["aw_date_order.calendar_year"],
            }
        )
        total = sum(float(r["aw_internet_sales.sales_amount"]) for r in rows)
        assert total == pytest.approx(ETALON_INTERNET, abs=TOL)

    def test_m2m_allocation_no_fanout(self, aw, rest):
        """Σ аллокации == выручка строк, У КОТОРЫХ есть причины (M2M-семантика)."""
        rows = rest({"measures": ["aw_sales_reason.allocated_sales_amount"]})
        ref = float(
            aw.execute(
                'SELECT SUM(f."SalesAmount") FROM aw.dbo."FactInternetSales" f '
                'WHERE EXISTS (SELECT 1 FROM aw.dbo."FactInternetSalesReason" b WHERE '
                ' b."SalesOrderNumber" = f."SalesOrderNumber" '
                ' AND b."SalesOrderLineNumber" = f."SalesOrderLineNumber")'
            ).fetchone()[0]
        )
        assert _m(rows, "aw_sales_reason.allocated_sales_amount") == pytest.approx(ref, abs=TOL)


class TestDerivedMeasures:
    def test_gross_profit_is_sum_of_differences(self, aw, rest):
        rows = rest({"measures": ["aw_internet_sales.gross_profit"]})
        ref = float(
            aw.execute(
                'SELECT SUM("SalesAmount" - "TotalProductCost") FROM aw.dbo."FactInternetSales"'
            ).fetchone()[0]
        )
        assert _m(rows, "aw_internet_sales.gross_profit") == pytest.approx(ref, abs=TOL)

    def test_margin_is_ratio_of_sums_not_avg(self, rest):
        rows = rest({"measures": ["aw_internet_sales.gross_profit_margin"]})
        margin = _m(rows, "aw_internet_sales.gross_profit_margin")
        assert 0.40 < margin < 0.42  # канон AW: ~41.1%

    def test_summary_channel_orders(self, rest):
        rows = rest(
            {
                "measures": ["aw_sales_summary.order_count"],
                "dimensions": ["aw_sales_summary.sales_channel"],
            }
        )
        by = {
            r["aw_sales_summary.sales_channel"]: int(r["aw_sales_summary.order_count"])
            for r in rows
        }
        assert by["Internet"] == 27659
        assert by["Reseller"] == 3796

    def test_mov_monthly_sum_equals_total(self, rest):
        rows = rest({"measures": ["aw_sales_mov.revenue"]})
        total = sum(float(r["aw_sales_mov.revenue"]) for r in rows)
        assert total == pytest.approx(ETALON_INTERNET + ETALON_RESELLER, abs=0.5)

    def test_product_ratios_sum_to_one(self, rest):
        rows = rest(
            {
                "measures": ["aw_product_ratios.amount"],
                "dimensions": ["aw_product_ratios.ratio_to_all"],
                "filters": [
                    {
                        "member": "aw_product_ratios.level",
                        "operator": "equals",
                        "values": ["category"],
                    }
                ],
            }
        )
        assert sum(float(r["aw_product_ratios.ratio_to_all"]) for r in rows) == pytest.approx(
            1.0, abs=1e-9
        )


class TestUnaryEmulation:
    """Унарные операторы плана счетов (§4.1)."""

    def test_balance_sheet_root_is_zero(self, rest):
        """Минусы Liabilities/Equity сводят баланс: итог корня (key=1) ≈ 0."""
        rows = rest(
            {
                "measures": ["aw_account_flat.amount_signed"],
                "filters": [
                    {
                        "member": "aw_account_flat.ancestor_key",
                        "operator": "equals",
                        "values": ["1"],
                    }
                ],
            }
        )
        assert abs(_m(rows, "aw_account_flat.amount_signed")) < 0.01

    def test_leaf_total_equals_fact_sum(self, rest):
        rows = rest({"measures": ["aw_account_flat.amount_leaf"]})
        assert _m(rows, "aw_account_flat.amount_leaf") == pytest.approx(ETALON_FINANCE, abs=TOL)

    def test_employee_flat_ceo_total(self, aw, rest):
        """Все продажи замыкаются на корень орг-лестницы (CEO без родителя)."""
        ceo = float(
            aw.execute(
                'SELECT "EmployeeKey" FROM aw.dbo."DimEmployee" '
                'WHERE "ParentEmployeeKey" IS NULL ORDER BY 1 LIMIT 1'
            ).fetchone()[0]
        )
        rows = rest(
            {
                "measures": ["aw_employee_flat.reseller_sales_amount"],
                "filters": [
                    {
                        "member": "aw_employee_flat.ancestor_key",
                        "operator": "equals",
                        "values": [str(ceo)],
                    }
                ],
            }
        )
        assert _m(rows, "aw_employee_flat.reseller_sales_amount") == pytest.approx(
            ETALON_RESELLER, abs=TOL
        )


class TestExchangeRates:
    def test_last_eod_matches_argmax_sql(self, aw, rest):
        rows = rest(
            {
                "measures": ["aw_exchange_rates.last_end_of_day_rate"],
                "dimensions": ["aw_dim_currency.currency_alternate_key"],
                "filters": [
                    {
                        "member": "aw_dim_currency.currency_alternate_key",
                        "operator": "equals",
                        "values": ["GBP"],
                    }
                ],
            }
        )
        ref = float(
            aw.execute(
                'SELECT "EndOfDayRate" FROM aw.dbo."FactCurrencyRate" r '
                'JOIN aw.dbo."DimCurrency" c ON c."CurrencyKey" = r."CurrencyKey" '
                'WHERE c."CurrencyAlternateKey" = \'GBP\' ORDER BY r."DateKey" DESC LIMIT 1'
            ).fetchone()[0]
        )
        assert _m(rows, "aw_exchange_rates.last_end_of_day_rate") == pytest.approx(ref, abs=1e-6)


class TestKpi:
    def test_net_income_consistent_with_account_flat(self, rest):
        """KPI net_income.value == aw_account_flat.amount_signed(счёт 47, Actual)."""
        kpi = _m(
            rest(
                {
                    "dimensions": ["aw_kpi.value_dim"],
                    "filters": [
                        {"member": "aw_kpi.kpi", "operator": "equals", "values": ["net_income"]}
                    ],
                }
            ),
            "aw_kpi.value_dim",
        )
        flat = _m(
            rest(
                {
                    "measures": ["aw_account_flat.amount_signed"],
                    "filters": [
                        {
                            "member": "aw_account_flat.ancestor_key",
                            "operator": "equals",
                            "values": ["47"],
                        },
                        {
                            "member": "aw_account_flat.scenario_key",
                            "operator": "equals",
                            "values": ["1"],
                        },
                    ],
                }
            ),
            "aw_account_flat.amount_signed",
        )
        assert kpi == pytest.approx(flat, abs=TOL)

    def test_kpi_row_count(self, rest):
        rows = rest({"dimensions": ["aw_kpi.kpi", "aw_kpi.member"]})
        # 12 KPI; product_gross_profit_margin разворачивается на 4 категории
        assert len(rows) >= 12
        assert any(
            r["aw_kpi.kpi"] == "product_gross_profit_margin" and r["aw_kpi.member"] == "Bikes"
            for r in rows
        )
