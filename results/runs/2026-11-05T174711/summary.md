# Оценка: 2026-11-05T174711

_commit `5f97567`, N=3 итераций на путь_

REST — `/v1/load` c `renewQuery` (кэш Cube отключён); SQL API — pg-wire `:15432`; REF — эталонный SQL к DuckDB.

| Вопрос | rows | parity | REST p50 (min), мс | SQL API p50 (min), мс | REF p50 (min), мс | SQL-хэш | файл | Evidence |
|---|---|---|---|---|---|---|---|---|
| `total_revenue` | 1 | OK | 14 (12) | 58 (57) | 7 (6) | `5f83be1c14be` | [SQL](../queries/total_revenue.sql) | [дашборд](http://localhost:3000/verification#total_revenue) |
| `revenue_by_year` | 7 | OK | 13 (12) | 59 (57) | 18 (17) | `26c7e763547c` | [SQL](../queries/revenue_by_year.sql) | [дашборд](http://localhost:3000/verification#revenue_by_year) |
| `revenue_by_region` | 5 | OK | 13 (11) | 18 (15) | 188 (175) | `e2fb3e5c67e5` | [SQL](../queries/revenue_by_region.sql) | [дашборд](http://localhost:3000/verification#revenue_by_region) |
| `revenue_by_segment` | 5 | OK | 12 (11) | 18 (17) | 172 (170) | `5668bc23fcdb` | [SQL](../queries/revenue_by_segment.sql) | [дашборд](http://localhost:3000/verification#revenue_by_segment) |
| `orders_by_status` | 3 | OK | 13 (12) | 20 (19) | 248 (246) | `f3fb185ac4ac` | [SQL](../queries/orders_by_status.sql) | [дашборд](http://localhost:3000/verification#orders_by_status) |
| `revenue_1997_by_quarter` | 4 | OK | 13 (13) | 60 (37) | 15 (13) | `53b589e6d713` | [SQL](../queries/revenue_1997_by_quarter.sql) | [дашборд](http://localhost:3000/verification#revenue_1997_by_quarter) |
| `avg_discount_by_ship_mode` | 7 | OK | 16 (12) | 55 (35) | 15 (14) | `31ca22275c57` | [SQL](../queries/avg_discount_by_ship_mode.sql) | [дашборд](http://localhost:3000/verification#avg_discount_by_ship_mode) |
| `quantity_by_part_type_top10` | 10 | OK | 16 (13) | 17 (16) | 363 (354) | `4e8aa1e9e247` | [SQL](../queries/quantity_by_part_type_top10.sql) | [дашборд](http://localhost:3000/verification#quantity_by_part_type_top10) |
| `revenue_by_supplier_region` | 5 | OK | 15 (12) | 16 (15) | 66 (65) | `65cee38a1bc9` | [SQL](../queries/revenue_by_supplier_region.sql) | [дашборд](http://localhost:3000/verification#revenue_by_supplier_region) |
| `lines_by_return_flag` | 3 | OK | 14 (12) | 59 (34) | 11 (11) | `58034a433121` | [SQL](../queries/lines_by_return_flag.sql) | [дашборд](http://localhost:3000/verification#lines_by_return_flag) |
| `revenue_1996_by_month` | 12 | OK | 13 (13) | 58 (32) | 13 (13) | `743e313c8ad2` | [SQL](../queries/revenue_1996_by_month.sql) | [дашборд](http://localhost:3000/verification#revenue_1996_by_month) |
| `top5_customer_nations_by_revenue` | 5 | OK | 13 (11) | 17 (16) | 185 (183) | `2adc51b9a449` | [SQL](../queries/top5_customer_nations_by_revenue.sql) | [дашборд](http://localhost:3000/verification#top5_customer_nations_by_revenue) |
| `sales_mov_1997` | 12 | OK | 13 (13) | 21 (17) | 66 (65) | `687d9913f545` | [SQL](../queries/sales_mov_1997.sql) | [дашборд](http://localhost:3000/verification#sales_mov_1997) |
| `aw_fact_by_quarter_2012` | 4 | OK | 13 (10) | 58 (27) | 8 (5) | `0e0ca2d72d65` | [SQL](../queries/aw_fact_by_quarter_2012.sql) | [дашборд](http://localhost:3000/verification#aw_fact_by_quarter_2012) |
| `aw_quota_vs_actual_quarters_2012` | 4 | OK | 12 (11) | 57 (28) | 6 (6) | `ee4118e4e04a` | [SQL](../queries/aw_quota_vs_actual_quarters_2012.sql) | [дашборд](http://localhost:3000/verification#aw_quota_vs_actual_quarters_2012) |
| `aw_quota_vs_actual_months_2012_q1` | 4 | OK | 15 (12) | 56 (29) | 8 (7) | `1a1d6ab7875a` | [SQL](../queries/aw_quota_vs_actual_months_2012_q1.sql) | [дашборд](http://localhost:3000/verification#aw_quota_vs_actual_months_2012_q1) |

**Итог**: 16 вопросов, паритет 16/16.
