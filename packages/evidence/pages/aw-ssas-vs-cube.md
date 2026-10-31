---
title: "AW: SSAS vs Cube"
---

# Adventure Works: SSAS Multidimensional → Cube

> **Назначение:** витрина миграции аналитического куба SSAS MD (AW2019SSISMD)
> в семантический слой Cube. Источник — RU-база `aw_dw2019_ru.duckdb`
> (AdventureWorksDW2019). 12 KPI, ролевые даты, унарные операторы плана счетов,
> M2M «причины покупок» — всё живёт в метаданных Cube
> (`packages/cube/model/cubes/aw_*.cube.yml`), доступно ИИ-агенту (MCP/REST)
> и SQL-клиентам. Детали и статусы переноса — `docs/ssasmd-cube-migration.md`.

## KPI (SSAS-узлы Kpi → меры aw_kpi)

```sql kpi
select * from cube.aw_kpi order by folder, kpi, member
```

<DataTable data={kpi} rows=all>
  <Column id=kpi title="KPI" />
  <Column id=member title="Элемент" />
  <Column id=title title="Название" />
  <Column id=value fmt=num2 title="Значение" align=right />
  <Column id=target fmt=num2 title="Цель" align=right />
  <Column id=status title="Статус" align=center />
  <Column id=unit title="Ед." />
</DataTable>

*Статус: 1 — цель достигнута, 0 — близко, −1 — не достигнута (KpiStatus из MDX).*

## Выручка по годам и каналам (ролевая дата заказа)

```sql by_year
select * from cube.aw_summary_by_year order by year, channel
```

<BarChart data={by_year} x=year y=sales_amount series=channel name="Выручка по каналам" />

## Товарные категории (снежинка Product → Subcategory → Category)

```sql by_cat
select * from cube.aw_product_categories order by sales_amount desc
```

<BarChart data={by_cat} x=category y=sales_amount name="Выручка по категориям" />

<DataTable data={by_cat} rows=12>
  <Column id=category title="Категория" />
  <Column id=subcategory title="Подкатегория" />
  <Column id=sales_amount fmt=num2 title="Выручка" align=right />
  <Column id=gross_profit fmt=num2 title="Валовая прибыль" align=right />
</DataTable>

## Что проверено (golden-тесты `packages/harness/tests/test_aw_golden.py`)

- Тоталы: интернет **29 358 677.22** + опт **80 450 596.98** = сводный **109 809 274.20** USD
- Анти-фан-аут: Σ по категориям/странам/годам == тоталы; M2M-аллокация без двойного счёта
- Унарные операторы: корень плана счетов (Balance Sheet) = 0; листовой тотал == ΣFactFinance
- 20 golden-тестов в общем прогоне harness (`just verify`)
