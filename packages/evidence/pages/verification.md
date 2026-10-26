---
title: "Верификация: 13 golden-вопросов"
---

# Верификация: 13 golden-вопросов

> **Назначение страницы:** кросс-сверка цифр. Каждый блок ниже помечен, **что он
> проверяет** и где используется в дашбордах. SQL каждого вопроса хранится в
> `sources/cube/<id>.sql` и выполняется **дословно через Cube SQL API** при
> материализации (`npx evidence sources`) — тот же текст, что гоняет harness.
>
> Harness-артефакты: `artifacts/verify-report.md` (rows-паритет REST ↔ SQL API ↔
> reference, детерминизм SQL, ground truth) · `results/index.md` (производительность).
> Ссылки на блоки: `http://localhost:3000/verification#<id>`.

## total_revenue

> **Проверяет:** общую выручку — все пути дают одну сумму.
> **Используется:** KPI на [Выручке](/revenue).

```sql
SELECT SUM(sales.revenue) AS total_revenue FROM sales
```

```sql v_total_revenue
select "sum(sales.revenue)" as total_revenue from cube.total_revenue
```

<BigValue data={v_total_revenue} value=total_revenue fmt=num2 title="Σ выручка (REST = SQL API = REF)" />

## revenue_by_year

> **Проверяет:** выручку по годам (ship-календарь) — основа календарного измерения.
> **Используется:** контекст всех временных разрезов.

```sql
SELECT sales.year, SUM(sales.revenue) FROM sales
GROUP BY sales.year ORDER BY sales.year
```

```sql v_revenue_by_year
select * from cube.revenue_by_year
```
<DataTable data={v_revenue_by_year} rows=all />
## revenue_by_region

> **Проверяет:** Какова выручка по регионам клиентов?
> **Используется:** BarChart «Выручка по регионам» на [Выручке](/revenue)

```sql
SELECT sales.customer_region, SUM(sales.revenue) FROM sales GROUP BY sales.customer_region ORDER BY sales.customer_region
```

```sql v_revenue_by_region
select * from cube.revenue_by_region
```
<DataTable data={v_revenue_by_region} rows=all />
## revenue_by_segment

> **Проверяет:** Какова выручка по рыночным сегментам клиентов?
> **Используется:** BarChart «Выручка по сегментам» на [Выручке](/revenue)

```sql
SELECT sales.market_segment, SUM(sales.revenue) FROM sales GROUP BY sales.market_segment ORDER BY sales.market_segment
```

```sql v_revenue_by_segment
select * from cube.revenue_by_segment
```
<DataTable data={v_revenue_by_segment} rows=all />
## orders_by_status

> **Проверяет:** Сколько заказов по каждому статусу?
> **Используется:** здоровье воронки заказов (F/O/P)

```sql
SELECT sales.order_status, COUNT(DISTINCT sales.orders_count) FROM sales GROUP BY sales.order_status ORDER BY sales.order_status
```

```sql v_orders_by_status
select * from cube.orders_by_status
```
<DataTable data={v_orders_by_status} rows=all />
## revenue_1997_by_quarter

> **Проверяет:** Какова выручка по кварталам 1997 года?
> **Используется:** квартальные срезы годовых отчётов

```sql
SELECT sales.quarter, SUM(sales.revenue) FROM sales WHERE sales.year = 1997 GROUP BY sales.quarter ORDER BY sales.quarter
```

```sql v_revenue_1997_by_quarter
select * from cube.revenue_1997_by_quarter
```
<DataTable data={v_revenue_1997_by_quarter} rows=all />
## avg_discount_by_ship_mode

> **Проверяет:** Каков средний дисконт по способам доставки?
> **Используется:** таблица скидок на [Доставке](/shipping)

```sql
SELECT sales.ship_mode, AVG(sales.avg_discount) FROM sales GROUP BY sales.ship_mode ORDER BY sales.ship_mode
```

```sql v_avg_discount_by_ship_mode
select * from cube.avg_discount_by_ship_mode
```
<DataTable data={v_avg_discount_by_ship_mode} rows=all />
## quantity_by_part_type_top10

> **Проверяет:** Топ-10 типов деталей по суммарному количеству?
> **Используется:** топ номенклатуры деталей

```sql
SELECT sales.part_type, SUM(sales.quantity) FROM sales GROUP BY sales.part_type ORDER BY SUM(sales.quantity) DESC LIMIT 10
```

```sql v_quantity_by_part_type_top10
select * from cube.quantity_by_part_type_top10
```
<DataTable data={v_quantity_by_part_type_top10} rows=all />
## revenue_by_supplier_region

> **Проверяет:** Какова выручка по регионам поставщиков?
> **Используется:** срезы по поставщикам

```sql
SELECT sales.supplier_region, SUM(sales.revenue) FROM sales GROUP BY sales.supplier_region ORDER BY sales.supplier_region
```

```sql v_revenue_by_supplier_region
select * from cube.revenue_by_supplier_region
```
<DataTable data={v_revenue_by_supplier_region} rows=all />
## lines_by_return_flag

> **Проверяет:** Сколько строк продаж по флагам возврата?
> **Используется:** BarChart возвратов на [Доставке](/shipping)

```sql
SELECT sales.return_flag, COUNT(sales.lines_count) FROM sales GROUP BY sales.return_flag ORDER BY sales.return_flag
```

```sql v_lines_by_return_flag
select * from cube.lines_by_return_flag
```
<DataTable data={v_lines_by_return_flag} rows=all />
## revenue_1996_by_month

> **Проверяет:** Какова выручка по месяцам 1996 года?
> **Используется:** месячные ряды [Отклонений](/revenue-mov)

```sql
SELECT sales.month, SUM(sales.revenue) FROM sales WHERE sales.year = 1996 GROUP BY sales.month ORDER BY sales.month
```

```sql v_revenue_1996_by_month
select * from cube.revenue_1996_by_month
```
<DataTable data={v_revenue_1996_by_month} rows=all />
## top5_customer_nations_by_revenue

> **Проверяет:** Топ-5 стран клиентов по выручке?
> **Используется:** топ [Клиентов](/top-clients)

```sql
SELECT sales.customer_nation, SUM(sales.revenue) FROM sales GROUP BY sales.customer_nation ORDER BY SUM(sales.revenue) DESC LIMIT 5
```

```sql v_top5_customer_nations_by_revenue
select * from cube.top5_customer_nations_by_revenue
```
<DataTable data={v_top5_customer_nations_by_revenue} rows=all />
## sales_mov_1997

> **Проверяет:** Каковы месячная выручка и отклонения YoY/PoP за 1997 (куб sales_mov)?
> **Используется:** куб `sales_mov`: YoY/PoP отклонения на [Отклонениях](/revenue-mov) — считаются в Cube, не в BI и не в таблице DuckDB

```sql
SELECT sales_mov.month, sales_mov.revenue_ly, sales_mov.rel_yoy, sales_mov.rel_pop, SUM(sales_mov.revenue) FROM sales_mov WHERE sales_mov.year = 1997 GROUP BY sales_mov.month, sales_mov.revenue_ly, sales_mov.rel_yoy, sales_mov.rel_pop ORDER BY sales_mov.month
```

```sql v_sales_mov_1997
select * from cube.sales_mov where year = 1997
```
<DataTable data={v_sales_mov_1997} rows=all />
