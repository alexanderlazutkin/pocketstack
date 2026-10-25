SELECT sum("fact_sales".net_price) "sales__revenue" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
LIMIT 10000