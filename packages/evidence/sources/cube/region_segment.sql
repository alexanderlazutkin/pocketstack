SELECT sales.customer_region AS region, sales.market_segment AS segment, SUM(sales.revenue) AS revenue
FROM sales GROUP BY sales.customer_region, sales.market_segment
