-- Ф11.1: квоты по кварталам × страна сотрудника (раздельный запрос стороны
-- плана: emp-фильтр в одномерном запросе точен; канон SSAS Sales Targets).
SELECT plan_vs_fact_blend.calendar_year AS year,
       plan_vs_fact_blend.calendar_quarter AS quarter,
       plan_vs_fact_blend.emp_territory_country AS country,
       SUM(plan_vs_fact_blend.sales_amount_quota) AS quota
FROM plan_vs_fact_blend
GROUP BY 1, 2, 3
HAVING SUM(plan_vs_fact_blend.sales_amount_quota) IS NOT NULL
