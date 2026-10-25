SELECT "fact_sales".return_flag "sales__return_flag", count("fact_sales".order_id * 100 + "fact_sales".line_number) "sales__lines_count" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
GROUP BY 1
ORDER BY  1  ASC
LIMIT 10000