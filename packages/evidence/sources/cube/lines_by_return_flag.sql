SELECT sales.return_flag, COUNT(sales.lines_count) FROM sales GROUP BY sales.return_flag ORDER BY sales.return_flag
