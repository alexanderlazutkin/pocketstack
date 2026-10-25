SELECT sales.supplier_region, SUM(sales.revenue) FROM sales GROUP BY sales.supplier_region ORDER BY sales.supplier_region
