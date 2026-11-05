-- Ф11.2: месячные строки план/факт (куб aw_quota_pace; квартал-строки
-- исключены — итоги квартала в aw_quota_vs_actual_quarters).
-- quota_display — display-дубль квоты квартала на каждом месяце (SSAS:
-- значение грубого grain на листьях, в подитоге не суммируется).
SELECT aw_quota_pace.calendar_year AS year,
       aw_quota_pace.calendar_quarter AS quarter,
       aw_quota_pace.month_number AS month,
       aw_quota_pace.month_name AS month_name,
       aw_quota_pace.sales_territory_country AS country,
       SUM(aw_quota_pace.quarter_quota) AS quota_display,
       SUM(aw_quota_pace.sales_amount) AS actual,
       aw_quota_pace.fact_share_of_quarter_quota AS fact_share,
       aw_quota_pace.cum_share_of_year_quota AS cum_share
FROM aw_quota_pace
WHERE aw_quota_pace.month_number IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, aw_quota_pace.fact_share_of_quarter_quota,
         aw_quota_pace.cum_share_of_year_quota
