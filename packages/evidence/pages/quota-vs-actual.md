---
title: "AW: План/факт (квоты vs оптовые продажи)"
---

# План/факт: квоты против оптовых продаж

> **Назначение:** демонстрация корректного расчёта метрик **на разных уровнях
> гранулярности**. План (`[Sales Amount Quota]`, FactSalesQuota) живёт на
> гранулярности **сотрудник × квартал**, факт (`[Reseller Sales Amount]`,
> FactResellerSales) — **строка заказа (день)**. Обе метрики — в одном кубе
> `aw_quota_vs_actual` (mixed grain), все вычисления — **Cube**: свёртки,
> отклонения и `completion = Σфакт / Σквота` (деление сумм, не среднее
> отношений). Страница только фильтрует. Сверка — golden-тесты
> `packages/harness/tests/test_aw_golden.py::TestQuotaVsActual`, методика —
> `docs/ssasmd-cube-migration.md` §8.1 (Ф11).

<Dropdown name=year>
    <DropdownOption value=2013 valueLabel="2013" />
    <DropdownOption value=2012 valueLabel="2012" />
    <DropdownOption value=2011 valueLabel="2011" />
    <DropdownOption value=2010 valueLabel="2010" />
</Dropdown>

<Dropdown name=country>
    <DropdownOption value="United States" valueLabel="United States" />
    <DropdownOption value="Canada" valueLabel="Canada" />
    <DropdownOption value="France" valueLabel="France" />
    <DropdownOption value="Germany" valueLabel="Germany" />
    <DropdownOption value="United Kingdom" valueLabel="United Kingdom" />
    <DropdownOption value="Australia" valueLabel="Australia" />
    <DropdownOption value="NA" valueLabel="NA (внутр.)" />
</Dropdown>

```sql kpi
select * from cube.aw_quota_vs_actual_kpi
where year = ${inputs.year.value} and country = '${inputs.country.value}'
```

<BigValue data={kpi} value=quota fmt=num0 title="План (квоты), USD" />
<BigValue data={kpi} value=actual fmt=num0 title="Факт (опт), USD" />
<BigValue data={kpi} value=variance fmt=num0 title="Δ Факт−план, USD" />
<BigValue data={kpi} value=completion_pct fmt=pct1 title="Выполнение плана" />

## По кварталам — общая гранулярность плана и факта

```sql quarters
select * from cube.aw_quota_vs_actual_quarters
where year = ${inputs.year.value} and country = '${inputs.country.value}'
order by quarter
```

<BarChart data={quarters} x=quarter y=actual name="Факт" y2=quota name2="План" />

<DataTable data={quarters} rows=all>
  <Column id=quarter title="Квартал" align=right />
  <Column id=quota title="План (квота)" fmt=num0 align=right />
  <Column id=actual title="Факт (опт)" fmt=num0 align=right />
  <Column id=variance title="Δ Факт−план" fmt=num0 align=right contentType=colorscale scaleColor=business />
  <Column id=completion_pct title="Выполнение" fmt=pct1 align=right contentType=colorscale scaleColor=business />
</DataTable>

*Квота есть только там, где задана в FactSalesQuota (например, Q4 последних
лет может быть без плана — тогда факт есть, план NULL).*

## По месяцам — гранулярность ниже плана

```sql months
select * from cube.aw_quota_vs_actual_months
where year = ${inputs.year.value} and country = '${inputs.country.value}'
order by quarter, month nulls first
```

<DataTable data={months} rows=all>
  <Column id=quarter title="Квартал" align=right />
  <Column id=month_name title="Месяц" />
  <Column id=quota title="План (квота)" fmt=num0 align=right />
  <Column id=actual title="Факт (опт)" fmt=num0 align=right />
</DataTable>

Строка **без месяца** — план-строка квартала (гранулярность квоты).
В строках месяцев план всегда пуст: квартальную квоту нельзя размазать по
месяцам — она появляется только при свёртке до квартала и выше.

<Details title="Методика: метрики на разных гранулярностях">
  - **План** — FactSalesQuota: сотрудник × квартал, USD. Годы 2010–2013.
  - **Факт** — FactResellerSales: строки заказов дилеров, дата заказа.
  - **Куб** `aw_quota_vs_actual` хранит строки двух гранулярностей:
    квартальные план-строки (месяц NULL) и месячные факт-строки (квота NULL);
    обе стороны предагрегированы до своей гранулярности — джойн не фанаутит.
  - **Территория** — страна сотрудника (DimEmployee → DimSalesTerritory),
    conformed для плана и факта; не территория сделки.
  - **Выполнение плана** на любом срезе = Σфакт / Σквота (деление сумм).
    На месячном срезе — NULL: план квартальный, среднее отношений дало бы
    искажение (гипотеза Г2, golden-тест `test_completion_is_ratio_of_sums`).
  - **Месячный срез** — факт есть, план NULL (Г3); Σ месяцев квартала ==
    факту квартала — свёртка без потерь и дублей (Г1).
</Details>
