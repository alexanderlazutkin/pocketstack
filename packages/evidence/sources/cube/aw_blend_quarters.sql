-- Ф11.1 (blending): план/факт по кварталам через view plan_vs_fact_blend —
-- каждый факт агрегируется в своём CTE, сводка по осям aw_dim_date.
-- Пустые годы календаря (обе меры NULL) отфильтрованы.
SELECT plan_vs_fact_blend.calendar_year AS year,
       plan_vs_fact_blend.calendar_quarter AS quarter,
       SUM(plan_vs_fact_blend.sales_amount_quota) AS quota,
       SUM(plan_vs_fact_blend.sales_amount) AS actual,
       plan_vs_fact_blend.completion_pct AS completion_pct
FROM plan_vs_fact_blend
GROUP BY 1, 2, plan_vs_fact_blend.completion_pct
HAVING SUM(plan_vs_fact_blend.sales_amount_quota) IS NOT NULL
    OR SUM(plan_vs_fact_blend.sales_amount) IS NOT NULL
