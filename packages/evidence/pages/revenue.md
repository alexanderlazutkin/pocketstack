---
title: "Выручка: регионы и сегменты"
---

# Выручка: регионы и сегменты

> **Назначение:** бизнес-дашборд «где мы зарабатываем». Все метрики вычислены
> **Cube** (материализация `sources/cube/kpi.sql`, `by_region.sql`, `by_segment.sql`,
> `region_segment.sql` — SQL выполнен через Cube SQL API), страница только фильтрует.
> Сверка цифр — [Верификация](verification) (`total_revenue`, `revenue_by_region`, `revenue_by_segment`).

```sql kpi
select * from cube.kpi
```

<BigValue data={kpi} value=total_revenue fmt=num2 title="Выручка, всего" />
<BigValue data={kpi} value=orders fmt=num0 title="Заказы" />

```sql by_region
select * from cube.by_region
```

```sql by_segment
select * from cube.by_segment
```

<Grid cols=2>
  <BarChart data={by_region} x=region y=revenue name="Выручка по регионам" />
  <BarChart data={by_segment} x=segment y=revenue name="Выручка по сегментам" />
</Grid>

## Разрез регион × сегмент

```sql region_segment
select * from cube.region_segment
```

<DataTable data={region_segment} rows=all sort="revenue desc">
  <Column id=region title="Регион" />
  <Column id=segment title="Сегмент" />
  <Column id=revenue title="Выручка" fmt=num2 align=right />
</DataTable>
