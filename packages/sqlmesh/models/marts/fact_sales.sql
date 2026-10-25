MODEL (
  name marts.fact_sales,
  kind FULL,
  audits [
    not_null(columns := (order_id, customer_id, part_id, supplier_id, line_number)),
    unique_combination_of_columns(columns := (order_id, line_number))
  ]
);

-- адаптация models/marts/fact_sales.sql; customer_id через orders (вместо link_order_customer)
SELECT
  li.l_orderkey     AS order_id,
  o.o_custkey       AS customer_id,
  li.l_partkey      AS part_id,
  li.l_suppkey      AS supplier_id,
  li.l_linenumber   AS line_number,
  li.l_quantity     AS quantity,
  li.l_extendedprice AS extended_price,
  li.l_discount     AS discount,
  li.l_tax          AS tax,
  li.l_returnflag   AS return_flag,
  li.l_linestatus   AS line_status,
  li.l_shipdate     AS ship_date,
  li.l_commitdate   AS commit_date,
  li.l_receiptdate  AS receipt_date,
  li.l_shipinstruct AS ship_instruct,
  li.l_shipmode     AS ship_mode,
  li.l_comment      AS comment,
  li.l_extendedprice * (1 - li.l_discount) AS net_price,
  li.l_extendedprice * (1 - li.l_discount) * (1 + li.l_tax) AS total_price_with_tax,
  date_diff('day', li.l_shipdate, li.l_receiptdate) AS days_in_transit
FROM raw_tpch.lineitem AS li
JOIN raw_tpch.orders AS o ON o.o_orderkey = li.l_orderkey
