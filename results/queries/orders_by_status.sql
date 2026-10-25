SELECT "dim_order".order_status "sales__order_status", COUNT(DISTINCT "fact_sales".order_id) "sales__orders_count" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
LEFT JOIN  pocketstack.marts.dim_order  AS "dim_order" ON "fact_sales".order_id = dim_order.order_id
GROUP BY 1
ORDER BY  1  ASC
LIMIT 10000