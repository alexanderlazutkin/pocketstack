# Оценка: 2026-10-26T145625

_commit `7f5f003`, N=3 итераций на путь_

REST — `/v1/load` c `renewQuery` (кэш Cube отключён); SQL API — pg-wire `:15432`; REF — эталонный SQL к DuckDB.

| Вопрос | rows | parity | REST p50 (min), мс | SQL API p50 (min), мс | REF p50 (min), мс | SQL-хэш | файл | Evidence |
|---|---|---|---|---|---|---|---|---|
| `total_revenue` | 1 | OK | 7 (5) | 49 (49) | 3 (3) | `5f83be1c14be` | [SQL](../queries/total_revenue.sql) | [дашборд](http://localhost:3000/verification#total_revenue) |
| `revenue_by_year` | 7 | OK | 9 (7) | 51 (49) | 6 (5) | `26c7e763547c` | [SQL](../queries/revenue_by_year.sql) | [дашборд](http://localhost:3000/verification#revenue_by_year) |
| `revenue_by_region` | 5 | OK | 8 (7) | 49 (41) | 20 (19) | `e2fb3e5c67e5` | [SQL](../queries/revenue_by_region.sql) | [дашборд](http://localhost:3000/verification#revenue_by_region) |
| `revenue_by_segment` | 5 | OK | 8 (6) | 49 (41) | 19 (19) | `5668bc23fcdb` | [SQL](../queries/revenue_by_segment.sql) | [дашборд](http://localhost:3000/verification#revenue_by_segment) |
| `orders_by_status` | 3 | OK | 6 (6) | 7 (7) | 36 (34) | `f3fb185ac4ac` | [SQL](../queries/orders_by_status.sql) | [дашборд](http://localhost:3000/verification#orders_by_status) |
| `revenue_1997_by_quarter` | 4 | OK | 7 (5) | 48 (16) | 4 (4) | `53b589e6d713` | [SQL](../queries/revenue_1997_by_quarter.sql) | [дашборд](http://localhost:3000/verification#revenue_1997_by_quarter) |
| `avg_discount_by_ship_mode` | 7 | OK | 6 (6) | 48 (47) | 4 (4) | `31ca22275c57` | [SQL](../queries/avg_discount_by_ship_mode.sql) | [дашборд](http://localhost:3000/verification#avg_discount_by_ship_mode) |
| `quantity_by_part_type_top10` | 10 | OK | 7 (6) | 47 (9) | 22 (22) | `4e8aa1e9e247` | [SQL](../queries/quantity_by_part_type_top10.sql) | [дашборд](http://localhost:3000/verification#quantity_by_part_type_top10) |
| `revenue_by_supplier_region` | 5 | OK | 8 (5) | 47 (29) | 14 (13) | `65cee38a1bc9` | [SQL](../queries/revenue_by_supplier_region.sql) | [дашборд](http://localhost:3000/verification#revenue_by_supplier_region) |
| `lines_by_return_flag` | 3 | OK | 8 (6) | 49 (48) | 4 (4) | `58034a433121` | [SQL](../queries/lines_by_return_flag.sql) | [дашборд](http://localhost:3000/verification#lines_by_return_flag) |
| `revenue_1996_by_month` | 12 | OK | 6 (6) | 49 (49) | 5 (4) | `743e313c8ad2` | [SQL](../queries/revenue_1996_by_month.sql) | [дашборд](http://localhost:3000/verification#revenue_1996_by_month) |
| `top5_customer_nations_by_revenue` | 5 | OK | 8 (5) | 48 (11) | 19 (18) | `2adc51b9a449` | [SQL](../queries/top5_customer_nations_by_revenue.sql) | [дашборд](http://localhost:3000/verification#top5_customer_nations_by_revenue) |
| `sales_mov_1997` | 12 | OK | 6 (6) | 50 (33) | 16 (15) | `687d9913f545` | [SQL](../queries/sales_mov_1997.sql) | [дашборд](http://localhost:3000/verification#sales_mov_1997) |

**Итог**: 13 вопросов, паритет 13/13.
