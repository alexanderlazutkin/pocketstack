-- Ф11.2: доли факта от плана на месячной оси (куб aw_quota_pace).
-- fact_share = факт_м / квота квартала; cum_share = Σфакт янв..м / квота года.
SELECT aw_quota_pace.calendar_year AS year,
       aw_quota_pace.calendar_quarter AS quarter,
       aw_quota_pace.month_number AS month,
       aw_quota_pace.month_name AS month_name,
       aw_quota_pace.sales_territory_country AS country,
       SUM(aw_quota_pace.sales_amount) AS actual,
       aw_quota_pace.fact_share_of_quarter_quota AS fact_share,
       aw_quota_pace.cum_share_of_year_quota AS cum_share
FROM aw_quota_pace
GROUP BY 1, 2, 3, 4, 5, aw_quota_pace.fact_share_of_quarter_quota,
         aw_quota_pace.cum_share_of_year_quota
