-- Ф11.1: факт (опт) по кварталам × страна сделки (раздельный запрос стороны
-- факта: deal-фильтр точен; канон SSAS Reseller Sales — территория заказа).
SELECT plan_vs_fact_blend.calendar_year AS year,
       plan_vs_fact_blend.calendar_quarter AS quarter,
       plan_vs_fact_blend.deal_territory_country AS country,
       SUM(plan_vs_fact_blend.sales_amount) AS actual
FROM plan_vs_fact_blend
GROUP BY 1, 2, 3
HAVING SUM(plan_vs_fact_blend.sales_amount) IS NOT NULL
