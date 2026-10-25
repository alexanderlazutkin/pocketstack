SELECT sales.ship_mode AS mode, AVG(sales.days_in_transit) AS avg_days, MAX(sales.days_in_transit) AS max_days
FROM sales GROUP BY sales.ship_mode ORDER BY avg_days DESC
