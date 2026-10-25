SELECT "dim_customer".customer_region "sales__customer_region", sum("fact_sales".net_price) "sales__revenue" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
LEFT JOIN  pocketstack.marts.dim_customer  AS "dim_customer" ON "fact_sales".customer_id = dim_customer.customer_id
GROUP BY 1
ORDER BY  1  ASC
LIMIT 10000