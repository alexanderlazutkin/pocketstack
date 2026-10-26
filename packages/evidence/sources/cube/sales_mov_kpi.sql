SELECT sales_mov.year,
       SUM(sales_mov.revenue) AS revenue,
       SUM(sales_mov.abs_yoy_sum) AS abs_yoy_sum,
       AVG(sales_mov.rel_yoy_avg) AS rel_yoy_avg
FROM sales_mov
GROUP BY sales_mov.year
ORDER BY sales_mov.year
