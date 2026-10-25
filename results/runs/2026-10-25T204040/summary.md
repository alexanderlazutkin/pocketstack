# Оценка: 2026-10-25T204040

_commit `11f8009`, N=3 итераций на путь_

REST — `/v1/load` c `renewQuery` (кэш Cube отключён); SQL API — pg-wire `:15432`; REF — эталонный SQL к DuckDB.

| Вопрос | rows | parity | REST p50 (min), мс | SQL API p50 (min), мс | REF p50 (min), мс | SQL-хэш | файл |
|---|---|---|---|---|---|---|---|
| `total_revenue` | 1 | OK | 8 (7) | 50 (48) | 3 (3) | `5f83be1c14be` | [SQL](../queries/total_revenue.sql) |
| `revenue_by_year` | 7 | OK | 9 (7) | 52 (51) | 6 (6) | `26c7e763547c` | [SQL](../queries/revenue_by_year.sql) |
| `revenue_by_region` | 5 | OK | 7 (6) | 48 (40) | 20 (19) | `e2fb3e5c67e5` | [SQL](../queries/revenue_by_region.sql) |
| `revenue_by_segment` | 5 | OK | 9 (6) | 52 (37) | 20 (19) | `5668bc23fcdb` | [SQL](../queries/revenue_by_segment.sql) |
| `orders_by_status` | 3 | OK | 6 (6) | 11 (8) | 39 (37) | `f3fb185ac4ac` | [SQL](../queries/orders_by_status.sql) |
| `revenue_1997_by_quarter` | 4 | OK | 6 (5) | 49 (17) | 5 (4) | `53b589e6d713` | [SQL](../queries/revenue_1997_by_quarter.sql) |
| `avg_discount_by_ship_mode` | 7 | OK | 8 (5) | 50 (50) | 4 (4) | `31ca22275c57` | [SQL](../queries/avg_discount_by_ship_mode.sql) |
| `quantity_by_part_type_top10` | 10 | OK | 7 (6) | 50 (10) | 25 (22) | `4e8aa1e9e247` | [SQL](../queries/quantity_by_part_type_top10.sql) |
| `revenue_by_supplier_region` | 5 | OK | 10 (6) | 50 (29) | 14 (14) | `65cee38a1bc9` | [SQL](../queries/revenue_by_supplier_region.sql) |
| `lines_by_return_flag` | 3 | OK | 6 (6) | 49 (48) | 4 (3) | `58034a433121` | [SQL](../queries/lines_by_return_flag.sql) |
| `revenue_1996_by_month` | 12 | OK | 7 (7) | 53 (51) | 6 (5) | `743e313c8ad2` | [SQL](../queries/revenue_1996_by_month.sql) |
| `top5_customer_nations_by_revenue` | 5 | OK | 6 (6) | 49 (10) | 20 (20) | `2adc51b9a449` | [SQL](../queries/top5_customer_nations_by_revenue.sql) |

**Итог**: 12 вопросов, паритет 12/12.
