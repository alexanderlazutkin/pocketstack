SELECT SUM(sales.revenue) AS total_revenue, COUNT(DISTINCT sales.orders_count) AS orders FROM sales
