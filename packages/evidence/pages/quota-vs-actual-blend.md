---
title: "AW: План/факт — data blending (пример 2)"
---

# План/факт: квоты vs оптовые продажи — data blending

> **Назначение:** второй способ сведения плана и факта — **data blending** в
> Cube (view `plan_vs_fact_blend`), без объединения данных в SQL одного куба.
> Каждый факт (квоты `aw_sales_targets`, опт `aw_reseller_sales`) агрегируется
> **в своём подзапросе** по conformed-осям `aw_dim_date` (год, квартал),
> затем агрегаты join'ятся — фанаут невозможен по построению. Срез —
> **год/квартал** (общий grain сторон). Сравнение подходов и почему здесь нет
> месяца и страны — `docs/ssasmd-cube-migration.md` §8.2; первый способ
> (mixed-grain куб) — [План/факт, пример 1](/quota-vs-actual).

<Dropdown name=year>
    <DropdownOption value=2013 valueLabel="2013" />
    <DropdownOption value=2012 valueLabel="2012" />
    <DropdownOption value=2011 valueLabel="2011" />
    <DropdownOption value=2010 valueLabel="2010" />
</Dropdown>

```sql kpi
select * from cube.aw_blend_kpi where year = ${inputs.year.value}
```

<BigValue data={kpi} value=quota fmt=num0 title="План (квоты), USD" />
<BigValue data={kpi} value=actual fmt=num0 title="Факт (опт), USD" />
<BigValue data={kpi} value=completion_pct fmt=pct1 title="Выполнение плана" />

## По кварталам — общий grain плана и факта

```sql quarters
select * from cube.aw_blend_quarters where year = ${inputs.year.value} order by quarter
```

<BarChart data={quarters} x=quarter y=actual name="Факт" y2=quota name2="План" />

<DataTable data={quarters} rows=all>
  <Column id=quarter title="Квартал" align=right />
  <Column id=quota title="План (квота)" fmt=num0 align=right />
  <Column id=actual title="Факт (опт)" fmt=num0 align=right />
  <Column id=completion_pct title="Выполнение" fmt=pct1 align=right contentType=colorscale scaleColor=business />
</DataTable>

Числа идентичны примеру 1 (mixed-grain куб) на срезах год/квартал —
сверка: golden-тесты `TestPlanVsFactBlend` (паритет с REF) и `TestQuotaVsActual`.

<Details title="Как считается (принцип blending-механики Cube 1.8.13)">
  - View `plan_vs_fact_blend` объявляет **два факта и общие оси** (члены
    aw_dim_date); никакой SQL объединения не пишется.
  - При запросе мер из обоих фактов Cube генерирует **CTE на каждый куб**:
    `dim LEFT JOIN факт_k GROUP BY ось` — каждая сторона суммируется
    **изолированно** (анти-фанаут), затем агрегаты соединяются LEFT JOIN по
    значениям осей (полный SQL — `/v1/sql`, ключ `plan_vs_fact_blend`).
  - `completion_pct` — **мера view**: выражение
    `aw_reseller_sales.sales_amount / NULLIF(aw_sales_targets.sales_amount_quota, 0)`
    (ссылки на меры кубов) вычисляется **над готовыми агрегатами** после
    сведения — деление сумм, корректное на любом срезе ≥ общего grain.
  - **Почему только год/квартал:** квота джойнится к дате первого дня
    квартала; ось «месяц» ложно отнесла бы всю квартальную квоту к одному
    месяцу. Месячный срез — только через mixed-grain куб (пример 1).
  - **Почему нет страны:** у квот нет пути к территории, кроме как через
    сотрудника; conformed-оси этого view — только даты.
  - **Пустые годы** в сыром ответе (2005–2014) — календарь DimDate шире
    данных; отфильтрованы в sources (`HAVING`).
</Details>
