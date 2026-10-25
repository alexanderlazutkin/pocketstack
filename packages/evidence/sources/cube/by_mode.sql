SELECT sales.ship_mode AS mode, SUM(sales.revenue) AS revenue, AVG(sales.avg_discount) AS avg_discount
FROM sales GROUP BY sales.ship_mode ORDER BY revenue DESC
