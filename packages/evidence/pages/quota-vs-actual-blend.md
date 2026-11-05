---
title: "AW: План/факт — data blending (пример 2)"
---

# План/факт: квоты vs оптовые продажи — data blending

> **Назначение:** второй способ сведения плана и факта — **data blending** в
> Cube (view `plan_vs_fact_blend`), без объединения данных в SQL одного куба.
> Каждый факт (квоты `aw_sales_targets`, опт `aw_reseller_sales`) агрегируется
> **в своём подзапросе** по conformed-осям `aw_dim_date` (год, квартал),
> затем агрегаты join'ятся — фанаут невозможен по построению. Страна
> применяются **раздельными запросами по сторонам** (как measure groups в
> SSAS): план фильтруется по стране сотрудника, факт — по стране сделки.
> Сравнение подходов — `docs/ssasmd-cube-migration.md` §8.2; первый способ
> (mixed-grain куб, обе стороны по стране сотрудника) — План/факт, пример 1.

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
</Dropdown>

```sql kpi
select * from cube.aw_blend_kpi where year = ${inputs.year.value}
```

<BigValue data={kpi} value=quota fmt=num0 title="План (квоты), USD — все страны" />
<BigValue data={kpi} value=actual fmt=num0 title="Факт (опт), USD — все страны" />
<BigValue data={kpi} value=completion_pct fmt=pct1 title="Выполнение, все страны" />

*План/факт вместе (и `completion`) считаются одним запросом blending — без
страны: объединение country-фильтров обеих сторон в одном запросе ломает
изоляцию подзапросов (Cube 1.8.13, §8.2 ограничение 9). Со страной стороны
считаются раздельно — ниже.*

## По кварталам со страной — раздельные запросы (канон SSAS)

Квоты — по стране **сотрудника** (referenced dim, как SSAS Sales Targets);
факт — по стране **сделки** (как SSAS Reseller Sales).

```sql quotas_country
select * from cube.aw_blend_quotas_country
where year = ${inputs.year.value} and country = '${inputs.country.value}'
order by quarter
```

```sql actuals_country
select * from cube.aw_blend_actuals_country
where year = ${inputs.year.value} and country = '${inputs.country.value}'
order by quarter
```

<Grid cols=2>
  <DataTable data={quotas_country} rows=all>
    <Column id=quarter title="Квартал" align=right />
    <Column id=country title="Страна (сотрудник)" />
    <Column id=quota title="План (квота)" fmt=num0 align=right />
  </DataTable>
  <DataTable data={actuals_country} rows=all>
    <Column id=quarter title="Квартал" align=right />
    <Column id=country title="Страна (сделка)" />
    <Column id=actual title="Факт (опт)" fmt=num0 align=right />
  </DataTable>
</Grid>

*Факт по стране сделки ≠ факту по стране сотрудника (пример 1): Canada 2013
≈ 5.2M по сделке против 3.9M по сотруднику — conformed по измерению не значит
conformed по семантике. Числа сторон сверены golden-тестами
`test_territory_country_filters`.*

## По месяцам — гранулярность ниже плана

Месячная ось в blending приписывает **всю квартальную квоту конкретному
месяцу** — туда, куда указывает DateKey строки квоты (источник AW датирован
«примерно квартальными» днями: 20120331, 20110701, 20101229…). Слева —
blending (искажение), справа — правильный месячный срез mixed-grain куба
(пример 1): план NULL на каждом месяце.

```sql months_blend
select * from cube.aw_blend_months where year = ${inputs.year.value} order by month
```

```sql months_mixed
select * from cube.aw_pace_months
where year = ${inputs.year.value} and country = '${inputs.country.value}'
order by quarter, month
```

<Grid cols=2>
  <DataTable data={months_blend} rows=all>
    <Column id=month title="Месяц" align=right />
    <Column id=quota title="План (квота)!" fmt=num0 align=right contentType=colorscale scaleColor=business />
    <Column id=actual title="Факт (опт)" fmt=num0 align=right />
  </DataTable>
  <DataTable data={months_mixed} rows=all>
    <Column id=quarter title="Кв." align=right />
    <Column id=month_name title="Месяц" />
    <Column id=quota_display title="План (квота кв.)" fmt=num0 align=right />
    <Column id=actual title="Факт (опт)" fmt=num0 align=right />
    <Column id=fact_share title="Доля факт/квота кв." fmt=pct1 align=right />
    <Column id=cum_share title="Кумулятив года" fmt=pct1 align=right contentType=colorscale scaleColor=business />
  </DataTable>
</Grid>

*Итог сравнения (2012, золотой-тест `test_month_slice_grain_distortion`):
Σ квот года в blending не меняется — ломается семантика, не арифметика:
вся квота квартала «проваливается» в один месяц (март), выполнение
«января» выглядит под 0%. Mixed-таблица (справа) — SSAS-стиль отображения:
план = display-дубль квоты квартала на каждом месяце, строка квартала —
итог по своей grain (план одинарный, факт = Σ месяцев; суммируемая мера
модели на месяце NULL — анти-утроение, Г3). Правило: ось среза мельче grain
стороны в blending — не использовать. Охват таблиц различается: blending —
все страны (фильтры сторон не объединяются в одном запросе), mixed —
выбранная страна, поэтому абсолютные величины планов различаются —
сравнивайте структуру, а не абсолюты.*

**Доли факта от плана** (правая таблица, куб `aw_quota_pace` — в blending
не выводится, нет знаменателя на месячной оси): месяц = `факт_м / квота
квартала` (Σ месяцев квартала == выполнение квартала), кумулятив года =
`Σфакт янв..м / квота года` (к декабрю == выполнению года). Уровни выше:
квартал = **100%** (квота целиком назначена кварталу), год = **NULL**
(годового плана нет — grain плана квартал); поуровневые определения
(SSAS Scope) в Cube 1.8 мерой не выражаются — §8.2.12. Инварианты —
golden `TestQuotaPace`.

<Details title="Как считается (принцип blending-механики Cube 1.8.13)">
  - View `plan_vs_fact_blend` объявляет **два факта и общие оси** (члены
    aw_dim_date); никакой SQL объединения не пишется.
  - При запросе мер из обоих фактов Cube генерирует **CTE на каждый куб**:
    `dim LEFT JOIN факт_k GROUP BY ось` — каждая сторона суммируется
    **изолированно** (анти-фанаут), затем агрегаты соединяются LEFT JOIN по
    значениям осей (полный SQL — `/v1/sql`, ключ `plan_vs_fact_blend`).
  - `completion_pct` — **мера view**: выражение над мерами двух кубов,
    вычисляется **над готовыми агрегатами** после сведения — деление сумм.
  - **Страна** — не ось сведения: у сторон разные join-пути к территории,
    единый dim-узел не сводится (дубли/потери). Workaround: предвычисленные
    члены `emp_territory_country` (квоты) и `deal_territory_country` (факт),
    применяются как фильтры — но только **по одному на запрос**: оба фильтра
    вместе протаскиваются во все подзапросы и режут чужую сторону (потеря
    строк; тест-фиксация `test_territory_filters_together_lose_rows`).
  - **Месяц** — ось мельче grain квот: квота приписывается месяцу по DateKey
    строки квоты (искажение; тест-фиксация
    `test_month_slice_grain_distortion`). Правильный месячный срез — пример 1.
  - **Пустые годы** календаря отфильтрованы в sources (HAVING).
</Details>
