SELECT sales.part_type, SUM(sales.quantity) FROM sales GROUP BY sales.part_type ORDER BY SUM(sales.quantity) DESC LIMIT 10
