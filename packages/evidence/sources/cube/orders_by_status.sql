SELECT sales.order_status, COUNT(DISTINCT sales.orders_count) FROM sales GROUP BY sales.order_status ORDER BY sales.order_status
