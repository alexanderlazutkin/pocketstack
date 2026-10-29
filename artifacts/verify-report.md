# pocketstack verify-report

_сгенерирован: 2026-10-28T22:27:35, commit `a2b558a`_

| Вопрос | rows: REST↔SQLAPI↔REF | SQL-hash (N прогонов) | ground truth (лог DuckDB) | Evidence |
|---|---|---|---|---|
| `total_revenue` | ✅ | ✅ `5f83be1c14be` | ✅ | [дашборд](http://localhost:3000/verification#total_revenue) |
| `revenue_by_year` | ✅ | ✅ `26c7e763547c` | ✅ | [дашборд](http://localhost:3000/verification#revenue_by_year) |
| `revenue_by_region` | ✅ | ✅ `e2fb3e5c67e5` | ✅ | [дашборд](http://localhost:3000/verification#revenue_by_region) |
| `revenue_by_segment` | ✅ | ✅ `5668bc23fcdb` | ✅ | [дашборд](http://localhost:3000/verification#revenue_by_segment) |
| `orders_by_status` | ✅ | ✅ `f3fb185ac4ac` | ✅ | [дашборд](http://localhost:3000/verification#orders_by_status) |
| `revenue_1997_by_quarter` | ✅ | ✅ `53b589e6d713` | ✅ | [дашборд](http://localhost:3000/verification#revenue_1997_by_quarter) |
| `avg_discount_by_ship_mode` | ✅ | ✅ `31ca22275c57` | ✅ | [дашборд](http://localhost:3000/verification#avg_discount_by_ship_mode) |
| `quantity_by_part_type_top10` | ✅ | ✅ `4e8aa1e9e247` | ✅ | [дашборд](http://localhost:3000/verification#quantity_by_part_type_top10) |
| `revenue_by_supplier_region` | ✅ | ✅ `65cee38a1bc9` | ✅ | [дашборд](http://localhost:3000/verification#revenue_by_supplier_region) |
| `lines_by_return_flag` | ✅ | ✅ `58034a433121` | ✅ | [дашборд](http://localhost:3000/verification#lines_by_return_flag) |
| `revenue_1996_by_month` | ✅ | ✅ `743e313c8ad2` | ✅ | [дашборд](http://localhost:3000/verification#revenue_1996_by_month) |
| `top5_customer_nations_by_revenue` | ✅ | ✅ `2adc51b9a449` | ✅ | [дашборд](http://localhost:3000/verification#top5_customer_nations_by_revenue) |
| `sales_mov_1997` | ✅ | ✅ `687d9913f545` | ✅ | [дашборд](http://localhost:3000/verification#sales_mov_1997) |

**Итог**: rows-паритет 13/13, SQL-детерминизм 13/13, ground truth 13/13.
