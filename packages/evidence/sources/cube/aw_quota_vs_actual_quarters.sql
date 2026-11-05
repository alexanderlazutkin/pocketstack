-- Ф11 план/факт по кварталам (общая гранулярность плана и факта) × страна.
SELECT aw_quota_vs_actual.calendar_year AS year,
       aw_quota_vs_actual.calendar_quarter AS quarter,
       aw_quota_vs_actual.sales_territory_country AS country,
       SUM(aw_quota_vs_actual.sales_amount_quota) AS quota,
       SUM(aw_quota_vs_actual.sales_amount) AS actual,
       aw_quota_vs_actual.completion_pct AS completion_pct,
       aw_quota_vs_actual.variance AS variance
FROM aw_quota_vs_actual
GROUP BY 1, 2, 3, aw_quota_vs_actual.completion_pct, aw_quota_vs_actual.variance
