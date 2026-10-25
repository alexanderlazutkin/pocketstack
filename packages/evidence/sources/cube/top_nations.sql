WITH t AS (SELECT sales.customer_nation AS nation, SUM(sales.revenue) AS revenue FROM sales GROUP BY sales.customer_nation),
g AS (SELECT SUM(revenue) AS total FROM t)
SELECT t.nation, t.revenue, 100.0*t.revenue/g.total AS share,
       100.0*SUM(t.revenue) OVER (ORDER BY t.revenue DESC)/g.total AS cum_share
FROM t, g ORDER BY t.revenue DESC
