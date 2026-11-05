-- Ф11.2: годовой уровень доли = NULL (годового плана в источнике нет,
-- grain плана — квартал; поуровневое определение, SSAS Scope-эмуляция).
SELECT aw_quota_vs_actual.calendar_year AS year,
       SUM(aw_quota_vs_actual.sales_amount_quota) AS quota,
       SUM(aw_quota_vs_actual.sales_amount) AS actual,
       CAST(NULL AS DOUBLE) AS quota_share
FROM aw_quota_vs_actual
GROUP BY 1
