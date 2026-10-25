SELECT sales.market_segment AS segment, SUM(sales.revenue) AS revenue FROM sales
GROUP BY sales.market_segment ORDER BY revenue DESC
