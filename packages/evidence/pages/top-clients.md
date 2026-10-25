---
title: "Топ клиентов"
---

# Топ клиентов по выручке

> **Назначение:** вклад крупнейших стран-клиентов: выручка, доля, накопленная доля
> (Парето). Метрики вычислены **Cube** (`sources/cube/top_nations.sql`), страница
> только отображает. Сверка — [Верификация](verification)
> (`top5_customer_nations_by_revenue`).

```sql top_nations
select * from cube.top_nations
```

<BarChart data={top_nations} x=nation y=revenue sort=revenue-desc name="Выручка по странам" />

## Таблица: вклад и накопленная доля

<DataTable data={top_nations} rows=15>
  <Column id=nation title="Страна" />
  <Column id=revenue title="Выручка" fmt=num2 align=right />
  <Column id=share title="Доля, %" fmt=pct1 align=right />
  <Column id=cum_share title="Накопл. доля, %" fmt=pct1 align=right contentType=colorscale scaleColor=business />
</DataTable>

<Details title="Почему страны, а не клиенты?">
  View `sales` открывает из `dim_customer` только аналитические атрибуты
  (нация, регион, сегмент) — персональных имён в семантике нет by design.
  «Клиент» здесь — страна клиента.
</Details>
