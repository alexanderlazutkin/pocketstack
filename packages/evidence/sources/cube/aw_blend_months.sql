-- Ф11.1, демонстрация ловушки grain: месяц-ось blending приписывает всю
-- квартальную квоту конкретному месяцу по DateKey строки квоты (источник
-- датирован «примерно квартальными» днями) — вместо NULL вне grain плана.
-- Правильный месяц-срез — cube.aw_quota_vs_actual_months (mixed grain).
SELECT plan_vs_fact_blend.calendar_year AS year,
       plan_vs_fact_blend.month_of_year AS month,
       SUM(plan_vs_fact_blend.sales_amount_quota) AS quota,
       SUM(plan_vs_fact_blend.sales_amount) AS actual
FROM plan_vs_fact_blend
GROUP BY 1, 2
HAVING SUM(plan_vs_fact_blend.sales_amount_quota) IS NOT NULL
    OR SUM(plan_vs_fact_blend.sales_amount) IS NOT NULL
