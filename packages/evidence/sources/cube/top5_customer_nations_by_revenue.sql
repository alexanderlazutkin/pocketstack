SELECT sales.customer_nation, SUM(sales.revenue) FROM sales GROUP BY sales.customer_nation ORDER BY SUM(sales.revenue) DESC LIMIT 5
