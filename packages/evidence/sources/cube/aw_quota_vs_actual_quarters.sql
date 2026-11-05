-- Ф11 план/факт по кварталам (общая гранулярность) × страна.
-- quota_share: квартальный уровень доли факта от плана = 100%
-- («квота целиком назначена кварталу» — поуровневое определение, Ф11.2).
SELECT aw_quota_vs_actual.calendar_year AS year,
       aw_quota_vs_actual.calendar_quarter AS quarter,
       aw_quota_vs_actual.sales_territory_country AS country,
       SUM(aw_quota_vs_actual.sales_amount_quota) AS quota,
       SUM(aw_quota_vs_actual.sales_amount) AS actual,
       aw_quota_vs_actual.completion_pct AS completion_pct,
       aw_quota_vs_actual.variance AS variance,
       SUM(aw_quota_vs_actual.sales_amount_quota)
         / NULLIF(SUM(aw_quota_vs_actual.sales_amount_quota), 0) AS quota_share
FROM aw_quota_vs_actual
GROUP BY 1, 2, 3, aw_quota_vs_actual.completion_pct, aw_quota_vs_actual.variance
