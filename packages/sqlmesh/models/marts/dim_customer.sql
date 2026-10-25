MODEL (
  name marts.dim_customer,
  kind FULL,
  audits [
    not_null(columns := (customer_id)),
    unique_values(columns := (customer_id))
  ]
);

-- адаптация models/marts/customer.sql (automate-dv-tpch): vault-joins -> natural keys raw_tpch
SELECT
  c.c_custkey    AS customer_id,
  c.c_custkey    AS customer_key,
  c.c_name       AS customer_name,
  c.c_address    AS customer_addr,
  n.n_name       AS customer_nation,
  r.r_name       AS customer_region,
  c.c_phone      AS customer_phone,
  c.c_acctbal    AS customer_acct_balance,
  c.c_mktsegment AS market_segment
FROM raw_tpch.customer AS c
JOIN raw_tpch.nation AS n ON n.n_nationkey = c.c_nationkey
JOIN raw_tpch.region AS r ON r.r_regionkey = n.n_regionkey
