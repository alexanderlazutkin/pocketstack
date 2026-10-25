SELECT sales.year, SUM(sales.revenue) FROM sales GROUP BY sales.year ORDER BY sales.year
