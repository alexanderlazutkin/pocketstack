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


class TestQuotaVsActual:
    """Ф11 (§8.1, plan.md №15): план/факт разных гранулярностей в одном кубе.

    aw_quota_vs_actual — смешанный grain: план-строки employee×quarter
    (SalesAmountQuota, месяц NULL) UNION ALL факт-строки employee×month
    (SalesAmount, GrossProfit, квота NULL). Территория — conformed через
    сотрудника (DimEmployee.SalesTerritoryKey). Гипотезы: Г1 паритет REF без
    фанаута; Г2 completion = деление сумм (не avg отношений); Г3 срез
    месяцем — план NULL, факт есть.
    """

    Q = "aw_quota_vs_actual"

    def test_quota_total(self, aw, rest):
        """Г1: Σ квот == FactSalesQuota (без фанаута от джойна с фактом)."""
        got = _m(
            rest({"measures": [f"{self.Q}.sales_amount_quota"]}), f"{self.Q}.sales_amount_quota"
        )
        ref = float(
            aw.execute('SELECT SUM("SalesAmountQuota") FROM aw.dbo."FactSalesQuota"').fetchone()[0]
        )
        assert got == pytest.approx(ref, abs=TOL)

    def test_actual_total(self, aw, rest):
        """Г1: Σ факта == FactResellerSales == эталон Ф9."""
        got = _m(rest({"measures": [f"{self.Q}.sales_amount"]}), f"{self.Q}.sales_amount")
        assert got == pytest.approx(ETALON_RESELLER, abs=TOL)

    def test_by_year(self, aw, rest):
        """Г1: по годам обе меры == REF (год факта — от даты заказа)."""
        rows = rest(
            {
                "measures": [f"{self.Q}.sales_amount_quota", f"{self.Q}.sales_amount"],
                "dimensions": [f"{self.Q}.calendar_year"],
            }
        )
        got_q = {
            int(r[f"{self.Q}.calendar_year"]): float(r[f"{self.Q}.sales_amount_quota"])
            for r in rows
        }
        got_a = {
            int(r[f"{self.Q}.calendar_year"]): float(r[f"{self.Q}.sales_amount"]) for r in rows
        }
        ref_q = {
            int(y): float(v)
            for y, v in aw.execute(
                'SELECT "CalendarYear", SUM("SalesAmountQuota") FROM aw.dbo."FactSalesQuota" GROUP BY 1'
            ).fetchall()
        }
        ref_a = {
            int(y): float(v)
            for y, v in aw.execute(
                'SELECT "OrderDateKey"//10000 AS y, SUM("SalesAmount") '
                'FROM aw.dbo."FactResellerSales" GROUP BY 1'
            ).fetchall()
        }
        assert set(got_q) == set(ref_q)
        assert set(got_a) == set(ref_a)
        for y in ref_q:
            assert got_q[y] == pytest.approx(ref_q[y], abs=TOL), f"квоты {y}"
        for y in ref_a:
            assert got_a[y] == pytest.approx(ref_a[y], abs=TOL), f"факт {y}"

    def test_completion_is_ratio_of_sums(self, aw, rest):
        """Г2: completion за год = Σфакт/Σквота ≠ среднее квартальных completion."""
        rows = rest(
            {
                "measures": [
                    f"{self.Q}.sales_amount_quota",
                    f"{self.Q}.sales_amount",
                    f"{self.Q}.completion_pct",
                ],
                "dimensions": [f"{self.Q}.calendar_year"],
            }
        )
        for r in rows:
            q = float(r[f"{self.Q}.sales_amount_quota"])
            a = float(r[f"{self.Q}.sales_amount"])
            c = r.get(f"{self.Q}.completion_pct")
            if c is None:
                assert a == pytest.approx(0, abs=TOL) or q == pytest.approx(0, abs=TOL)
            else:
                assert float(c) == pytest.approx(a / q, rel=1e-6)
        # деление сумм ≠ avg отношений: считаем оба варианта на REF-данных года
        y, q_sum, a_sum, avg_of_ratios = aw.execute(
            """
            WITH qq AS (
              SELECT "CalendarYear" y, "CalendarQuarter" qtr, SUM("SalesAmountQuota") v
              FROM aw.dbo."FactSalesQuota" GROUP BY 1, 2
            ), aa AS (
              SELECT "OrderDateKey"//10000 y, ((("OrderDateKey"//100)%100+2)//3) qtr,
                     SUM("SalesAmount") v
              FROM aw.dbo."FactResellerSales" GROUP BY 1, 2
            )
            SELECT qq.y, SUM(qq.v), SUM(COALESCE(aa.v, 0)),
                   AVG(CASE WHEN qq.v > 0 AND aa.v IS NOT NULL THEN aa.v / qq.v END)
            FROM qq LEFT JOIN aa USING (y, qtr)
            GROUP BY 1 ORDER BY SUM(qq.v) DESC LIMIT 1
            """
        ).fetchone()
        ratio_of_sums = float(a_sum) / float(q_sum)
        assert avg_of_ratios != pytest.approx(ratio_of_sums, rel=1e-3)
        got = {int(r[f"{self.Q}.calendar_year"]): r.get(f"{self.Q}.completion_pct") for r in rows}
        assert float(got[int(y)]) == pytest.approx(ratio_of_sums, rel=1e-6)

    def test_month_slice_quota_null(self, aw, rest):
        """Г3: срез месяцем — план NULL, факт есть; Σ месяцев квартала == REF."""
        year = int(
            aw.execute('SELECT MAX("CalendarYear") FROM aw.dbo."FactSalesQuota"').fetchone()[0]
        )
        quarter = int(
            aw.execute(
                'SELECT "CalendarQuarter" FROM aw.dbo."FactSalesQuota" WHERE "CalendarYear" = ? LIMIT 1',
                [year],
            ).fetchone()[0]
        )
        rows = rest(
            {
                "measures": [f"{self.Q}.sales_amount_quota", f"{self.Q}.sales_amount"],
                "dimensions": [
                    f"{self.Q}.calendar_year",
                    f"{self.Q}.calendar_quarter",
                    f"{self.Q}.month_number",
                ],
                "filters": [
                    {
                        "member": f"{self.Q}.calendar_year",
                        "operator": "equals",
                        "values": [str(year)],
                    },
                    {
                        "member": f"{self.Q}.calendar_quarter",
                        "operator": "equals",
                        "values": [str(quarter)],
                    },
                ],
            }
        )
        monthly = [r for r in rows if r.get(f"{self.Q}.month_number") is not None]
        assert monthly, "нет месячных строк факта"
        for r in monthly:
            assert r.get(f"{self.Q}.sales_amount_quota") is None, "план на месяце должен быть NULL"
            assert float(r[f"{self.Q}.sales_amount"]) > 0
        assert {int(r[f"{self.Q}.month_number"]) for r in monthly} <= {
            (quarter - 1) * 3 + 1,
            (quarter - 1) * 3 + 2,
            (quarter - 1) * 3 + 3,
        }
        ref = float(
            aw.execute(
                'SELECT COALESCE(SUM("SalesAmount"), 0) FROM aw.dbo."FactResellerSales" '
                'WHERE "OrderDateKey"//10000 = ? AND ((("OrderDateKey"//100)%100+2)//3) = ?',
                [year, quarter],
            ).fetchone()[0]
        )
        assert sum(float(r[f"{self.Q}.sales_amount"]) for r in monthly) == pytest.approx(
            ref, abs=TOL
        )

    def test_territory_country_conformed(self, aw, rest):
        """Г1/Ф11: страна — conformed через сотрудника (обе стороны DimEmployee)."""
        rows = rest(
            {
                "measures": [f"{self.Q}.sales_amount_quota", f"{self.Q}.sales_amount"],
                "dimensions": ["aw_dim_sales_territory.sales_territory_country"],
            }
        )
        got_q = {
            r["aw_dim_sales_territory.sales_territory_country"]: float(
                r[f"{self.Q}.sales_amount_quota"]
            )
            for r in rows
        }
        got_a = {
            r["aw_dim_sales_territory.sales_territory_country"]: float(r[f"{self.Q}.sales_amount"])
            for r in rows
        }
        ref_q = {
            c: float(v)
            for c, v in aw.execute(
                'SELECT t."SalesTerritoryCountry", SUM(q."SalesAmountQuota") '
                'FROM aw.dbo."FactSalesQuota" q JOIN aw.dbo."DimEmployee" e '
                '  ON q."EmployeeKey" = e."EmployeeKey" '
                'JOIN aw.dbo."DimSalesTerritory" t '
                '  ON t."SalesTerritoryKey" = e."SalesTerritoryKey" GROUP BY 1'
            ).fetchall()
        }
        ref_a = {
            c: float(v)
            for c, v in aw.execute(
                'SELECT t."SalesTerritoryCountry", SUM(r."SalesAmount") '
                'FROM aw.dbo."FactResellerSales" r JOIN aw.dbo."DimEmployee" e '
                '  ON r."EmployeeKey" = e."EmployeeKey" '
                'JOIN aw.dbo."DimSalesTerritory" t '
                '  ON t."SalesTerritoryKey" = e."SalesTerritoryKey" GROUP BY 1'
            ).fetchall()
        }
        assert set(got_q) == set(ref_q)
        assert set(got_a) == set(ref_a)
        for c in ref_q:
            assert got_q[c] == pytest.approx(ref_q[c], abs=TOL), f"квоты {c}"
        for c in ref_a:
            assert got_a[c] == pytest.approx(ref_a[c], abs=TOL), f"факт {c}"

    def test_employee_quarter_grain(self, aw, rest):
        """Г1: grain employee×quarter — квоты и факт без потерь/дублей."""
        rows = rest(
            {
                "measures": [f"{self.Q}.sales_amount_quota", f"{self.Q}.sales_amount"],
                "dimensions": [
                    f"{self.Q}.employee_key",
                    f"{self.Q}.calendar_year",
                    f"{self.Q}.calendar_quarter",
                ],
            }
        )
        got = {}
        for r in rows:
            k = (
                int(r[f"{self.Q}.employee_key"]),
                int(r[f"{self.Q}.calendar_year"]),
                int(r[f"{self.Q}.calendar_quarter"]),
            )
            q = r.get(f"{self.Q}.sales_amount_quota")
            a = r.get(f"{self.Q}.sales_amount")
            e = got.setdefault(k, [0.0, 0.0])
            e[0] += float(q) if q is not None else 0.0
            e[1] += float(a) if a is not None else 0.0
        ref_q = {
            (int(e), int(y), int(qq)): float(v)
            for e, y, qq, v in aw.execute(
                'SELECT "EmployeeKey", "CalendarYear", "CalendarQuarter", SUM("SalesAmountQuota") '
                'FROM aw.dbo."FactSalesQuota" GROUP BY 1,2,3'
            ).fetchall()
        }
        ref_a = {
            (int(e), int(y), int(qq)): float(v)
            for e, y, qq, v in aw.execute(
                'SELECT "EmployeeKey", "OrderDateKey"//10000, ((("OrderDateKey"//100)%100+2)//3), SUM("SalesAmount") '
                'FROM aw.dbo."FactResellerSales" GROUP BY 1,2,3'
            ).fetchall()
        }
        assert set(got) == set(ref_q) | set(ref_a)
        for k, v in ref_q.items():
            assert got[k][0] == pytest.approx(v, abs=TOL), f"квота {k}"
        for k, v in ref_a.items():
            assert got[k][1] == pytest.approx(v, abs=TOL), f"факт {k}"


class TestPlanVsFactBlend:
    """Ф11.1: тот же план/факт через data blending (multi-fact view).

    View plan_vs_fact_blend сводит меры aw_sales_targets (квоты) и
    aw_reseller_sales (опт) по conformed-осям aw_dim_date (год/квартал);
    completion_pct — мера view (выражение над мерами двух кубов). Сравнение
    с теми же REF, что и mixed-grain куб (TestQuotaVsActual): сведение по
    общему grain должно давать идентичные числа. Месячная ось НЕ входит:
    квота джойнится к DateKey первого дня квартала — на месяце она
    «провалилась» бы в один месяц (искажение grain, см. §8.2).
    """

    V = "plan_vs_fact_blend"

    def test_quota_total(self, aw, rest):
        got = _m(
            rest({"measures": [f"{self.V}.sales_amount_quota"]}), f"{self.V}.sales_amount_quota"
        )
        ref = float(
            aw.execute('SELECT SUM("SalesAmountQuota") FROM aw.dbo."FactSalesQuota"').fetchone()[0]
        )
        assert got == pytest.approx(ref, abs=TOL)

    def test_actual_total(self, aw, rest):
        got = _m(rest({"measures": [f"{self.V}.sales_amount"]}), f"{self.V}.sales_amount")
        assert got == pytest.approx(ETALON_RESELLER, abs=TOL)

    def test_by_year_matches_mixed_cube(self, aw, rest):
        """Blending == mixed-grain куб == REF: по годам обе меры."""
        rows = rest(
            {
                "measures": [f"{self.V}.sales_amount_quota", f"{self.V}.sales_amount"],
                "dimensions": [f"{self.V}.calendar_year"],
            }
        )
        # dim-корень звезды отдаёт и «пустые» годы календаря (обе меры NULL)
        got = {
            int(r[f"{self.V}.calendar_year"]): (
                float(r[f"{self.V}.sales_amount_quota"]),
                float(r[f"{self.V}.sales_amount"]),
            )
            for r in rows
            if r.get(f"{self.V}.sales_amount_quota") is not None
            or r.get(f"{self.V}.sales_amount") is not None
        }
        ref_q = {
            int(y): float(v)
            for y, v in aw.execute(
                'SELECT "CalendarYear", SUM("SalesAmountQuota") FROM aw.dbo."FactSalesQuota" GROUP BY 1'
            ).fetchall()
        }
        ref_a = {
            int(y): float(v)
            for y, v in aw.execute(
                'SELECT "OrderDateKey"//10000 AS y, SUM("SalesAmount") '
                'FROM aw.dbo."FactResellerSales" GROUP BY 1'
            ).fetchall()
        }
        assert set(got) == set(ref_q) | set(ref_a)
        for y in ref_q:
            assert got[y][0] == pytest.approx(ref_q[y], abs=TOL), f"квоты {y}"
        for y in ref_a:
            assert got[y][1] == pytest.approx(ref_a[y], abs=TOL), f"факт {y}"

    def test_completion_ratio_of_sums_by_quarter(self, aw, rest):
        """Г2: completion по кварталам = Σфакт/Σквота (деление сумм)."""
        rows = rest(
            {
                "measures": [
                    f"{self.V}.sales_amount_quota",
                    f"{self.V}.sales_amount",
                    f"{self.V}.completion_pct",
                ],
                "dimensions": [f"{self.V}.calendar_year", f"{self.V}.calendar_quarter"],
                "filters": [
                    {"member": f"{self.V}.calendar_year", "operator": "equals", "values": ["2012"]}
                ],
            }
        )
        assert rows
        for r in rows:
            q = r.get(f"{self.V}.sales_amount_quota")
            a = r.get(f"{self.V}.sales_amount")
            c = r.get(f"{self.V}.completion_pct")
            if q is None or float(q) == 0:
                assert c is None
            else:
                assert float(c) == pytest.approx(float(a) / float(q), rel=1e-6), r

    def test_territory_country_filters(self, aw, rest):
        """Ф11.1: страна — раздельные запросы по сторонам (канон SSAS:
        квота через emp_territory_country, факт через deal_territory_country).
        Фильтр каждой стороны в ОДНОМЕРНОМ запросе точен (pushdown в свой CTE).
        """
        country = "Canada"
        got_q = _m(
            rest(
                {
                    "measures": [f"{self.V}.sales_amount_quota"],
                    "dimensions": [f"{self.V}.calendar_year"],
                    "filters": [
                        {"member": f"{self.V}.calendar_year", "operator": "equals", "values": ["2012"]},
                        {"member": f"{self.V}.emp_territory_country", "operator": "equals", "values": [country]},
                    ],
                }
            ),
            f"{self.V}.sales_amount_quota",
        )
        got_a = _m(
            rest(
                {
                    "measures": [f"{self.V}.sales_amount"],
                    "dimensions": [f"{self.V}.calendar_year"],
                    "filters": [
                        {"member": f"{self.V}.calendar_year", "operator": "equals", "values": ["2012"]},
                        {"member": f"{self.V}.deal_territory_country", "operator": "equals", "values": [country]},
                    ],
                }
            ),
            f"{self.V}.sales_amount",
        )
        ref_q = float(
            aw.execute(
                'SELECT SUM(q."SalesAmountQuota") FROM aw.dbo."FactSalesQuota" q '
                'JOIN aw.dbo."DimEmployee" e ON q."EmployeeKey" = e."EmployeeKey" '
                'JOIN aw.dbo."DimSalesTerritory" t ON e."SalesTerritoryKey" = t."SalesTerritoryKey" '
                'WHERE q."CalendarYear" = 2012 AND t."SalesTerritoryCountry" = ?',
                [country],
            ).fetchone()[0]
        )
        ref_a = float(
            aw.execute(
                'SELECT SUM(r."SalesAmount") FROM aw.dbo."FactResellerSales" r '
                'JOIN aw.dbo."DimSalesTerritory" t ON r."SalesTerritoryKey" = t."SalesTerritoryKey" '
                'WHERE r."OrderDateKey"//10000 = 2012 AND t."SalesTerritoryCountry" = ?',
                [country],
            ).fetchone()[0]
        )
        assert got_q == pytest.approx(ref_q, abs=TOL)
        assert got_a == pytest.approx(ref_a, abs=TOL)

    def test_territory_filters_together_lose_rows(self, aw, rest):
        """Фиксация наблюдаемого бага 1.8.13 (§8.2, ограничение 9): оба
        country-фильтра в ОДНОМ запросе протаскиваются во все key-CTE —
        чужой фильтр режет сторону через NULL-семантику LEFT JOIN, факт
        теряет строки. После апгрейда Cube (multi_stage / изоляция фильтров)
        — заменить этот тест на строгий паритет."""
        country = "Canada"
        got_a = _m(
            rest(
                {
                    "measures": [f"{self.V}.sales_amount"],
                    "dimensions": [f"{self.V}.calendar_year"],
                    "filters": [
                        {"member": f"{self.V}.calendar_year", "operator": "equals", "values": ["2012"]},
                        {"member": f"{self.V}.emp_territory_country", "operator": "equals", "values": [country]},
                        {"member": f"{self.V}.deal_territory_country", "operator": "equals", "values": [country]},
                    ],
                }
            ),
            f"{self.V}.sales_amount",
        )
        ref_a = float(
            aw.execute(
                'SELECT SUM(r."SalesAmount") FROM aw.dbo."FactResellerSales" r '
                'JOIN aw.dbo."DimSalesTerritory" t ON r."SalesTerritoryKey" = t."SalesTerritoryKey" '
                'WHERE r."OrderDateKey"//10000 = 2012 AND t."SalesTerritoryCountry" = ?',
                [country],
            ).fetchone()[0]
        )
        assert got_a != pytest.approx(ref_a, abs=TOL), (
            "если факт сошёлся — Cube починил изоляцию фильтров, "
            "обнови §8.2 и этот тест"
        )
        assert got_a < ref_a  # наблюдаемое: потеря строк, не задвоение
    def test_month_slice_grain_distortion(self, aw, rest):
        """Ф11.1, демонстрация ловушки grain: ось «месяц» в blending приписывает
        ВСЮ квартальную квоту к конкретному месяцу по DateKey строки квоты
        (источник AW датирован «примерно квартальными» днями: 20110331,
        20110701, 20101229…) — вместо NULL вне grain плана. Σ года при этом
        сохраняется (искажение семантики, не арифметики). Правильное
        поведение (план NULL на любом месяце) — mixed-grain куб (пример 1)."""
        rows = rest(
            {
                "measures": [f"{self.V}.sales_amount_quota", f"{self.V}.sales_amount"],
                "dimensions": [f"{self.V}.calendar_year", f"{self.V}.month_of_year"],
                "filters": [
                    {"member": f"{self.V}.calendar_year", "operator": "equals", "values": ["2012"]}
                ],
            }
        )
        quota_by_month = {
            int(r[f"{self.V}.month_of_year"]): float(r[f"{self.V}.sales_amount_quota"])
            for r in rows
            if r.get(f"{self.V}.sales_amount_quota") is not None
        }
        ref_q_quarters = {
            q: float(v)
            for q, v in aw.execute(
                'SELECT "CalendarQuarter", SUM("SalesAmountQuota") '
                'FROM aw.dbo."FactSalesQuota" WHERE "CalendarYear" = 2012 GROUP BY 1'
            ).fetchall()
        }
        assert ref_q_quarters, "в 2012 должны быть квоты"
        # Σ месяцев == Σ года: арифметика цела
        assert sum(quota_by_month.values()) == pytest.approx(sum(ref_q_quarters.values()), abs=TOL)
        # каждый месяц с квотой лежит внутри своего квартала, и в квартале
        # ровно один такой месяц, вмещающий ВСЮ квартальную квоту
        for month, v in quota_by_month.items():
            quarter = (month - 1) // 3 + 1
            months_of_quarter = {m for m in quota_by_month if (m - 1) // 3 + 1 == quarter}
            assert months_of_quarter == {month}
            assert v == pytest.approx(ref_q_quarters[quarter], abs=TOL), (
                f"месяц {month}: вся квота Q{quarter} в одном месяце"
            )
        # контраст: mixed-grain куб (пример 1) на любом месяце — план NULL
        mixed = rest(
            {
                "measures": ["aw_quota_vs_actual.sales_amount_quota"],
                "dimensions": [
                    "aw_quota_vs_actual.calendar_year",
                    "aw_quota_vs_actual.month_number",
                ],
                "filters": [
                    {
                        "member": "aw_quota_vs_actual.calendar_year",
                        "operator": "equals",
                        "values": ["2012"],
                    }
                ],
            }
        )
        monthly_mixed = [r for r in mixed if r.get("aw_quota_vs_actual.month_number") is not None]
        assert monthly_mixed
        for r in monthly_mixed:
            assert r.get("aw_quota_vs_actual.sales_amount_quota") is None
