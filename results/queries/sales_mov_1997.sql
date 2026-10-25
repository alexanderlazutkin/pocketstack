SELECT "sales_mov".month "sales_mov__month", "sales_mov".revenue_ly "sales_mov__revenue_ly", "sales_mov".rel_yoy "sales_mov__rel_yoy", "sales_mov".rel_pop "sales_mov__rel_pop", sum("sales_mov".revenue) "sales_mov__revenue" 
FROM  (WITH m AS (
  SELECT d.year, d.month, SUM(f.net_price) AS revenue
  FROM pocketstack.marts.fact_sales f
  JOIN pocketstack.marts.dim_date d ON d.date_day = f.ship_date
  GROUP BY 1, 2
)
SELECT
  cur.year,
  cur.month,
  cur.revenue,
  ly.revenue    AS revenue_ly,
  cur.revenue - ly.revenue AS abs_yoy,
  CASE WHEN ly.revenue IS NULL OR ly.revenue = 0 THEN NULL
       ELSE 100.0 * (cur.revenue - ly.revenue) / ly.revenue END AS rel_yoy,
  prev.revenue  AS revenue_pop,
  cur.revenue - prev.revenue AS abs_pop,
  CASE WHEN prev.revenue IS NULL OR prev.revenue = 0 THEN NULL
       ELSE 100.0 * (cur.revenue - prev.revenue) / prev.revenue END AS rel_pop
FROM m cur
LEFT JOIN m ly   ON ly.year = cur.year - 1 AND ly.month = cur.month
LEFT JOIN m prev ON prev.year = cur.year AND prev.month = cur.month - 1
)  AS "sales_mov"
WHERE ("sales_mov".year = ?)
GROUP BY 1, 2, 3, 4
ORDER BY  1  ASC
LIMIT 10000