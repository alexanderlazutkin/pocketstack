MODEL (
  name marts.dim_date,
  kind FULL,
  audits [
    not_null(columns := (date_day, year, quarter, month, day)),
    unique_combination_of_columns(columns := (date_day))
  ]
);

-- Календарь дат: union-диапазон ship_date/receipt_date факта, grain — день, без пропусков.
-- range() в DuckDB возвращает TIMESTAMP → приводим к DATE; конецExclusive → +1 день.
WITH bounds AS (
  SELECT
    min(least(ship_date, receipt_date)) AS min_d,
    max(greatest(ship_date, receipt_date)) AS max_d
  FROM marts.fact_sales
)
SELECT
  CAST(d AS DATE) AS date_day,
  year(d)          AS year,
  quarter(d)       AS quarter,
  month(d)         AS month,
  day(d)           AS day
FROM bounds, range(min_d, max_d + INTERVAL 1 DAY, INTERVAL 1 DAY) AS t(d)
