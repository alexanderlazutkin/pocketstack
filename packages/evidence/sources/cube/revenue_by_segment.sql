SELECT sales.market_segment, SUM(sales.revenue) FROM sales GROUP BY sales.market_segment ORDER BY sales.market_segment
