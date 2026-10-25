SELECT "dim_part".part_type "sales__part_type", sum("fact_sales".quantity) "sales__quantity" 
FROM  pocketstack.marts.fact_sales  AS "fact_sales"
LEFT JOIN  pocketstack.marts.dim_part  AS "dim_part" ON "fact_sales".part_id = dim_part.part_id
GROUP BY 1
ORDER BY  2  DESC
LIMIT 10