SELECT sales.customer_region AS region, SUM(sales.revenue) AS revenue FROM sales
GROUP BY sales.customer_region ORDER BY revenue DESC
