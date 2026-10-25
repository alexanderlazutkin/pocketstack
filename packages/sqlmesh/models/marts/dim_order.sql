MODEL (
  name marts.dim_order,
  kind FULL,
  audits [
    not_null(columns := (order_id)),
    unique_values(columns := (order_id))
  ]
);

-- адаптация models/marts/customer_order.sql; normalize: order_hk -> order_id
SELECT
  o.o_orderkey      AS order_id,
  o.o_orderkey      AS order_key,
  o.o_orderstatus   AS order_status,
  o.o_totalprice    AS total_price,
  o.o_orderdate     AS order_date,
  o.o_orderpriority AS order_priority,
  o.o_clerk         AS clerk,
  o.o_shippriority  AS ship_priority
FROM raw_tpch.orders AS o
