SELECT "fact_sales".ship_mode "sales__ship_mode", avg("fact_sales".discount) "sales__avg_discount" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
GROUP BY 1
ORDER BY  1  ASC
LIMIT 10000