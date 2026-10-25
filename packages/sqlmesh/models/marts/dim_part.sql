MODEL (
  name marts.dim_part,
  kind FULL,
  audits [
    not_null(columns := (part_id)),
    unique_values(columns := (part_id))
  ]
);

-- адаптация models/marts/part.sql (automate-dv-tpch)
SELECT
  p.p_partkey     AS part_id,
  p.p_partkey     AS part_key,
  p.p_name        AS part_name,
  p.p_mfgr        AS manufacturer,
  p.p_brand       AS brand,
  p.p_type        AS part_type,
  p.p_size        AS part_size,
  p.p_container   AS part_container,
  p.p_retailprice AS part_retail_price
FROM raw_tpch.part AS p
