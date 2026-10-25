# pocketstack verify-report

_сгенерирован: 2026-10-25T20:42:18, commit `11f8009`_

| Вопрос | rows: REST↔SQLAPI↔REF | SQL-hash (N прогонов) | ground truth (лог DuckDB) |
|---|---|---|---|
| `total_revenue` | ✅ | ✅ `5f83be1c14be` | ✅ |
| `revenue_by_year` | ✅ | ✅ `26c7e763547c` | ✅ |
| `revenue_by_region` | ✅ | ✅ `e2fb3e5c67e5` | ✅ |
| `revenue_by_segment` | ✅ | ✅ `5668bc23fcdb` | ✅ |
| `orders_by_status` | ✅ | ✅ `f3fb185ac4ac` | ✅ |
| `revenue_1997_by_quarter` | ✅ | ✅ `53b589e6d713` | ✅ |
| `avg_discount_by_ship_mode` | ✅ | ✅ `31ca22275c57` | ✅ |
| `quantity_by_part_type_top10` | ✅ | ✅ `4e8aa1e9e247` | ✅ |
| `revenue_by_supplier_region` | ✅ | ✅ `65cee38a1bc9` | ✅ |
| `lines_by_return_flag` | ✅ | ✅ `58034a433121` | ✅ |
| `revenue_1996_by_month` | ✅ | ✅ `743e313c8ad2` | ✅ |
| `top5_customer_nations_by_revenue` | ✅ | ✅ `2adc51b9a449` | ✅ |

**Итог**: rows-паритет 12/12, SQL-детерминизм 12/12, ground truth 12/12.
