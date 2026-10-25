SELECT "dim_supplier".supplier_region "sales__supplier_region", sum("fact_sales".net_price) "sales__revenue" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
LEFT JOIN  pocketstack.marts.dim_supplier  AS "dim_supplier" ON "fact_sales".supplier_id = dim_supplier.supplier_id
GROUP BY 1
ORDER BY  1  ASC
LIMIT 10000