-- Ф11 план/факт по месяцам (гранулярность ниже плана: квота NULL у месячных
-- строк; строка month NULL — план-строка квартала) × страна.
SELECT aw_quota_vs_actual.calendar_year AS year,
       aw_quota_vs_actual.calendar_quarter AS quarter,
       aw_quota_vs_actual.month_number AS month,
       aw_quota_vs_actual.month_name AS month_name,
       aw_quota_vs_actual.sales_territory_country AS country,
       SUM(aw_quota_vs_actual.sales_amount_quota) AS quota,
       SUM(aw_quota_vs_actual.sales_amount) AS actual
FROM aw_quota_vs_actual
GROUP BY 1, 2, 3, 4, 5
