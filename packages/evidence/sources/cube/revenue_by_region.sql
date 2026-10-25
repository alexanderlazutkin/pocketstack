SELECT sales.customer_region, SUM(sales.revenue) FROM sales GROUP BY sales.customer_region ORDER BY sales.customer_region
