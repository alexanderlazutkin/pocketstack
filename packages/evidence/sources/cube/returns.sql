SELECT sales.return_flag AS flag, COUNT(sales.lines_count) AS lines, SUM(sales.revenue) AS revenue
FROM sales GROUP BY sales.return_flag
