-- Ф11.1 (blending): KPI план/факт по годам (деление сумм — мера view).
SELECT plan_vs_fact_blend.calendar_year AS year,
       SUM(plan_vs_fact_blend.sales_amount_quota) AS quota,
       SUM(plan_vs_fact_blend.sales_amount) AS actual,
       plan_vs_fact_blend.completion_pct AS completion_pct
FROM plan_vs_fact_blend
GROUP BY 1, plan_vs_fact_blend.completion_pct
HAVING SUM(plan_vs_fact_blend.sales_amount_quota) IS NOT NULL
    OR SUM(plan_vs_fact_blend.sales_amount) IS NOT NULL
