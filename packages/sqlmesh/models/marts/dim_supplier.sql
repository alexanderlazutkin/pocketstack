MODEL (
  name marts.dim_supplier,
  kind FULL,
  audits [
    not_null(columns := (supplier_id)),
    unique_values(columns := (supplier_id))
  ]
);

-- адаптация models/marts/supplier.sql; fix: алиас региона customer_region -> supplier_region
SELECT
  s.s_suppkey  AS supplier_id,
  s.s_suppkey  AS supplier_key,
  s.s_name     AS supplier_name,
  s.s_address  AS supplier_addr,
  n.n_name     AS supplier_nation,
  r.r_name     AS supplier_region,
  s.s_phone    AS supplier_phone,
  s.s_acctbal  AS supplier_acct_balance
FROM raw_tpch.supplier AS s
JOIN raw_tpch.nation AS n ON n.n_nationkey = s.s_nationkey
JOIN raw_tpch.region AS r ON r.r_regionkey = n.n_regionkey
