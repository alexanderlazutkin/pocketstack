SELECT sales.quarter, SUM(sales.revenue) FROM sales WHERE sales.year = 1997 GROUP BY sales.quarter ORDER BY sales.quarter
