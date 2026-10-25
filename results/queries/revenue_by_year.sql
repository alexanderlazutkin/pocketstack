SELECT "dim_date".year "sales__year", sum("fact_sales".net_price) "sales__revenue" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
LEFT JOIN  pocketstack.marts.dim_date  AS "dim_date" ON "fact_sales".ship_date = dim_date.date_day
GROUP BY 1
ORDER BY  1  ASC
LIMIT 10000