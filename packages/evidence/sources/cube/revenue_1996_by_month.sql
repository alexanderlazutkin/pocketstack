SELECT sales.month, SUM(sales.revenue) FROM sales WHERE sales.year = 1996 GROUP BY sales.month ORDER BY sales.month
