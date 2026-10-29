# Оценка: 2026-10-29T231246

_commit `71b865f`, N=3 итераций на путь_

REST — `/v1/load` c `renewQuery` (кэш Cube отключён); SQL API — pg-wire `:15432`; REF — эталонный SQL к DuckDB.

| Вопрос | rows | parity | REST p50 (min), мс | SQL API p50 (min), мс | REF p50 (min), мс | SQL-хэш | файл | Evidence |
|---|---|---|---|---|---|---|---|---|
| `total_revenue` | 1 | OK | 15 (13) | 58 (17) | 13 (12) | `5f83be1c14be` | [SQL](../queries/total_revenue.sql) | [дашборд](http://localhost:3000/verification#total_revenue) |
| `revenue_by_year` | 7 | OK | 15 (13) | 58 (17) | 20 (18) | `26c7e763547c` | [SQL](../queries/revenue_by_year.sql) | [дашборд](http://localhost:3000/verification#revenue_by_year) |
| `revenue_by_region` | 5 | OK | 16 (13) | 18 (17) | 29 (29) | `e2fb3e5c67e5` | [SQL](../queries/revenue_by_region.sql) | [дашборд](http://localhost:3000/verification#revenue_by_region) |
| `revenue_by_segment` | 5 | OK | 14 (12) | 16 (15) | 30 (27) | `5668bc23fcdb` | [SQL](../queries/revenue_by_segment.sql) | [дашборд](http://localhost:3000/verification#revenue_by_segment) |
| `orders_by_status` | 3 | OK | 14 (13) | 17 (15) | 50 (49) | `f3fb185ac4ac` | [SQL](../queries/orders_by_status.sql) | [дашборд](http://localhost:3000/verification#orders_by_status) |
| `revenue_1997_by_quarter` | 4 | OK | 14 (13) | 61 (58) | 21 (18) | `53b589e6d713` | [SQL](../queries/revenue_1997_by_quarter.sql) | [дашборд](http://localhost:3000/verification#revenue_1997_by_quarter) |
| `avg_discount_by_ship_mode` | 7 | OK | 14 (10) | 43 (15) | 14 (10) | `31ca22275c57` | [SQL](../queries/avg_discount_by_ship_mode.sql) | [дашборд](http://localhost:3000/verification#avg_discount_by_ship_mode) |
| `quantity_by_part_type_top10` | 10 | OK | 15 (12) | 17 (17) | 33 (32) | `4e8aa1e9e247` | [SQL](../queries/quantity_by_part_type_top10.sql) | [дашборд](http://localhost:3000/verification#quantity_by_part_type_top10) |
| `revenue_by_supplier_region` | 5 | OK | 15 (14) | 60 (20) | 24 (21) | `65cee38a1bc9` | [SQL](../queries/revenue_by_supplier_region.sql) | [дашборд](http://localhost:3000/verification#revenue_by_supplier_region) |
| `lines_by_return_flag` | 3 | OK | 12 (12) | 56 (44) | 13 (11) | `58034a433121` | [SQL](../queries/lines_by_return_flag.sql) | [дашборд](http://localhost:3000/verification#lines_by_return_flag) |
| `revenue_1996_by_month` | 12 | OK | 15 (14) | 60 (59) | 20 (20) | `743e313c8ad2` | [SQL](../queries/revenue_1996_by_month.sql) | [дашборд](http://localhost:3000/verification#revenue_1996_by_month) |
| `top5_customer_nations_by_revenue` | 5 | OK | 15 (14) | 20 (18) | 31 (30) | `2adc51b9a449` | [SQL](../queries/top5_customer_nations_by_revenue.sql) | [дашборд](http://localhost:3000/verification#top5_customer_nations_by_revenue) |
| `sales_mov_1997` | 12 | OK | 14 (14) | 19 (17) | 29 (28) | `687d9913f545` | [SQL](../queries/sales_mov_1997.sql) | [дашборд](http://localhost:3000/verification#sales_mov_1997) |

**Итог**: 13 вопросов, паритет 13/13.
