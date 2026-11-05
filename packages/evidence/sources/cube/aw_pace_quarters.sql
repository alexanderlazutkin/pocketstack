-- Ф11.2: квартальный уровень доли = 100% («квота целиком назначена кварталу» —
-- поуровневое определение, SSAS Scope-эмуляция: SUM(qq)/SUM(qq), не литерал).
SELECT aw_quota_vs_actual.calendar_year AS year,
       aw_quota_vs_actual.calendar_quarter AS quarter,
       SUM(aw_quota_vs_actual.sales_amount_quota) AS quota,
       SUM(aw_quota_vs_actual.sales_amount) AS actual,
       SUM(aw_quota_vs_actual.sales_amount_quota)
         / NULLIF(SUM(aw_quota_vs_actual.sales_amount_quota), 0) AS quota_share
FROM aw_quota_vs_actual
GROUP BY 1, 2
HAVING SUM(aw_quota_vs_actual.sales_amount_quota) IS NOT NULL
    OR SUM(aw_quota_vs_actual.sales_amount) IS NOT NULL
