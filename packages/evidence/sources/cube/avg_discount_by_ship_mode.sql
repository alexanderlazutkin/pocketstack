SELECT sales.ship_mode, AVG(sales.avg_discount) FROM sales GROUP BY sales.ship_mode ORDER BY sales.ship_mode
