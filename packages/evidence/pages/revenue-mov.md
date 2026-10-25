---
title: "Выручка по месяцам: отклонения"
---

# Выручка по месяцам: отклонения

> **Назначение:** динамика выручки с **абсолютными и относительными отклонениями**:
> к тому же месяцу прошлого года (YoY) и к предыдущему месяцу (PoP).
> Отклонения вычисляет **Cube** — куб `sales_mov` (логика в семантическом слое:
> `packages/cube/model/cubes/sales_mov.cube.yml`), материализуется запросом
> `sources/cube/sales_mov.sql` (все годы). Страница только выбирает год.
> Прошлые периоды — серым. Сверка — [Верификация](verification)
> (`revenue_1996_by_month`, `sales_mov_1997`).

<Dropdown name=year>
    <DropdownOption value=1997 valueLabel="1997" />
    <DropdownOption value=1996 valueLabel="1996" />
    <DropdownOption value=1995 valueLabel="1995" />
</Dropdown>

```sql mov
select * from cube.sales_mov where year = ${inputs.year.value} order by month
```

<BigValue data={mov} value=revenue fmt=num2 title="Выручка, Σ месяцев" summaryTotal />
<BigValue data={mov} value=abs_yoy fmt=num2 title="Δ YoY, абс." summarySum />
<BigValue data={mov} value=rel_yoy fmt=pct1 title="Δ YoY, %" summaryAvg />

## Текущий год против прошлого (прошлый год — серым)

<BarChart data={mov} x=month y=revenue name={inputs.year.value} y2=revenue_ly name2="прошлый год" />

## Таблица отклонений

<DataTable data={mov} rows=all>
  <Column id=month title="Месяц" align=right />
  <Column id=revenue title="Выручка" fmt=num2 align=right />
  <Column id=revenue_ly title="LY" fmt=num2 align=right />
  <Column id=abs_yoy title="Δ YoY, абс." fmt=num2 align=right contentType=colorscale scaleColor=business />
  <Column id=rel_yoy title="Δ YoY, %" fmt=pct1 align=right contentType=colorscale scaleColor=business />
  <Column id=revenue_pop title="Пред. мес." fmt=num2 align=right />
  <Column id=abs_pop title="Δ PoP, абс." fmt=num2 align=right contentType=colorscale scaleColor=business />
  <Column id=rel_pop title="Δ PoP, %" fmt=pct1 align=right contentType=colorscale scaleColor=business />
</DataTable>

<Details title="Методика">
  - **YoY** — месяц текущего года против того же месяца прошлого года.
  - **PoP** — против предыдущего месяца того же года (январь — пусто).
  - Отн. отклонение = (тек − база) / база × 100.
  - Данные TPC-H полны по 1992–1998 (заказы до 1998-08): сравнивайте годы ≤1997.
</Details>
