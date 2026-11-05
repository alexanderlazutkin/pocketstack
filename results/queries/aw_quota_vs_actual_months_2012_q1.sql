SELECT "aw_quota_vs_actual"."CalendarYear" "aw_quota_vs_actual__calendar_year", "aw_quota_vs_actual"."CalendarQuarter" "aw_quota_vs_actual__calendar_quarter", "aw_quota_vs_actual"."MonthNumber" "aw_quota_vs_actual__month_number", sum("aw_quota_vs_actual"."SalesAmountQuota") "aw_quota_vs_actual__sales_amount_quota", sum("aw_quota_vs_actual"."SalesAmount") "aw_quota_vs_actual__sales_amount" 
FROM  (WITH quota AS (
  SELECT
    q."EmployeeKey",
    e."SalesTerritoryKey",
    t."SalesTerritoryCountry",
    q."CalendarYear",
    q."CalendarQuarter",
    CAST(SUM(q."SalesAmountQuota") AS DOUBLE) AS sales_amount_quota
  FROM aw_dw2019_ru.dbo."FactSalesQuota" q
  JOIN aw_dw2019_ru.dbo."DimEmployee" e ON q."EmployeeKey" = e."EmployeeKey"
  JOIN aw_dw2019_ru.dbo."DimSalesTerritory" t ON t."SalesTerritoryKey" = e."SalesTerritoryKey"
  GROUP BY 1, 2, 3, 4, 5
),
actual AS (
  SELECT
    r."EmployeeKey",
    e."SalesTerritoryKey",
    t."SalesTerritoryCountry",
    r."OrderDateKey" // 10000 AS calendar_year,
    (((r."OrderDateKey" // 100) % 100) + 2) // 3 AS calendar_quarter,
    (r."OrderDateKey" // 100) % 100 AS month_number,
    CAST(SUM(r."SalesAmount") AS DOUBLE) AS sales_amount,
    CAST(SUM(r."SalesAmount" - r."TotalProductCost") AS DOUBLE) AS gross_profit
  FROM aw_dw2019_ru.dbo."FactResellerSales" r
  JOIN aw_dw2019_ru.dbo."DimEmployee" e ON r."EmployeeKey" = e."EmployeeKey"
  JOIN aw_dw2019_ru.dbo."DimSalesTerritory" t ON t."SalesTerritoryKey" = e."SalesTerritoryKey"
  GROUP BY 1, 2, 3, 4, 5, 6
)
SELECT
  'q:' || "EmployeeKey" || ':' || "CalendarYear" || ':' || "CalendarQuarter" AS "RowKey",
  "EmployeeKey", "SalesTerritoryKey", "SalesTerritoryCountry", "CalendarYear", "CalendarQuarter",
  NULL::INTEGER AS "MonthNumber",
  NULL::VARCHAR AS "MonthName",
  sales_amount_quota AS "SalesAmountQuota",
  NULL::DOUBLE AS "SalesAmount",
  NULL::DOUBLE AS "GrossProfit"
FROM quota
UNION ALL
SELECT
  'a:' || "EmployeeKey" || ':' || calendar_year || ':' || calendar_quarter || ':' || month_number AS "RowKey",
  "EmployeeKey",
  "SalesTerritoryKey",
  "SalesTerritoryCountry",
  calendar_year AS "CalendarYear",
  calendar_quarter AS "CalendarQuarter",
  month_number AS "MonthNumber",
  (['Январь','Февраль','Март','Апрель','Май','Июнь',
    'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'])[month_number] AS "MonthName",
  NULL::DOUBLE AS "SalesAmountQuota",
  sales_amount AS "SalesAmount",
  gross_profit AS "GrossProfit"
FROM actual
)  AS "aw_quota_vs_actual"
WHERE ("aw_quota_vs_actual"."CalendarYear" = ?) AND ("aw_quota_vs_actual"."CalendarQuarter" = ?)
GROUP BY 1, 2, 3
ORDER BY  4  DESC
LIMIT 10000