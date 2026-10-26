---
title: "Доставка"
---

# Доставка: способы, возвраты, дисциплина

> **Назначение:** shipping performance. Метрики вычислены **Cube**
> (`sources/cube/by_mode.sql`, `returns.sql`, `delay.sql`), страница только
> отображает. Сверка — [Верификация](/verification)
> (`avg_discount_by_ship_mode`, `lines_by_return_flag`).

```sql by_mode
select * from cube.by_mode
```

```sql returns
select * from cube.returns
```

```sql delay
select * from cube.delay
```

<Grid cols=2>
  <BigValue data={returns} value=lines fmt=num0 title="Строк всего" summaryTotal />
  <BigValue data={delay} value=avg_days fmt=num1 title="Ср. дней в пути" summaryAvg />
</Grid>

<Grid cols=2>
  <BarChart data={by_mode} x=mode y=revenue name="Выручка по способу доставки" />
  <BarChart data={returns} x=flag y=lines name="Строк по флагу возврата" />
</Grid>

## Скорость доставки по способам

<DataTable data={delay} rows=all>
  <Column id=mode title="Способ" />
  <Column id=avg_days title="Ср. дней от отгрузки до прихода" fmt=num1 align=right />
  <Column id=max_days title="Макс. дней" fmt=num0 align=right />
</DataTable>

<Details title="Флаги возврата">
  **A** (After) — сделка закрыта позже отгрузки; **R** (Returned) — возврат;
  **F** (Final) — сделка закрыта в момент отгрузки. Доли F/R — здоровье продаж.
</Details>
