SELECT sales_mov.year, sales_mov.month, SUM(sales_mov.revenue) AS revenue,
       sales_mov.revenue_ly, sales_mov.abs_yoy, sales_mov.rel_yoy,
       sales_mov.revenue_pop, sales_mov.abs_pop, sales_mov.rel_pop
FROM sales_mov
GROUP BY sales_mov.year, sales_mov.month, sales_mov.revenue_ly, sales_mov.abs_yoy,
         sales_mov.rel_yoy, sales_mov.revenue_pop, sales_mov.abs_pop, sales_mov.rel_pop
