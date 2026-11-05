# Миграция SSAS Multidimensional (AW2019SSASMD) → Cube

Версия: 1.1 (2026-10-31). Источник-проект: `~/Git/DB/sqlserver/mssql-server-samplesdb/AW2019SSASMD`
(Analysis Services Multidimensional, Enterprise Edition, схема AW DW 2019).
Целевой стек: Cube OSS 1.8.13 (self-hosted, docker-compose) поверх **`aw_dw2019_ru.duckdb`**
(RU-база с богатыми COMMENT ON — см. `MIGRATION.md` репозитория-источника).

> Контекст проекта: `plan.md` (стек/защитные правила), `cube-oss-vs-enterprise.md` (границы OSS),
> `cube-mcp.md` (AI-агент), `gotchas.md`.

## 1. Цель и принципы

1. Воспроизвести **аналитическую функциональность** куба Adventure Works в Cube: измерения,
   меры, иерархии, ролевые даты, KPI-показатели.
2. Источник — русская БД `aw_dw2019_ru.duckdb` (30 таблиц, 354 колонки, комментарии RU в
   `duckdb_columns().comment` / `duckdb_tables().comment`; словарь `aw_metadata.tsv`).
3. **Все метаданные Cube — на русском, самодостаточные для ИИ-агента**: каждый cube/measure/
   dimension/hierarchy получает `title` + `description` (формат как у `sales_mov`). ИИ-агент
   должен понимать семантику без обращения к SSAS-первоисточнику.
4. Правило защиты: `aw_dw2019_ru.duckdb` для Cube — **только чтение**; файл кладём в
   `warehouse/` рядом с `pocketstack.duckdb` (не в git; восстанавливается копией из
   репозитория-источника или повторным прогоном `migrate.sh`).

## 2. Инвентарь SSASMD-проекта (что реально есть)

| Объект | Кол-во | Состав / детали |
|---|---|---|
| Кубы | 1 | `Adventure Works` (MOLAP) |
| Группы мер (MG) | 11 | Internet Sales (9), Internet Orders, Internet Customers, Sales Reasons, Reseller Sales (11), Reseller Orders, Sales Summary (9), Sales Orders, Sales Targets, Financial Reporting, Exchange Rates |
| Базовые меры | 38 | Sum (~28 по умолчанию), Count ×4, **DistinctCount ×4** (Order/Customer Count и др.), None ×1 (Unit Price Discount %), **LastNonEmpty ×1** (End of Day Rate), **AverageOfChildren ×1** (Average Rate), **ByAccount ×1** (Amount) |
| Измерения в кубе | 19 уникальных | Customer, Product, Sales Territory, Sales Reason, Promotion, Currency, Destination Currency, Geography, Reseller, Employee, Sales Channel, Scenario, Account, Organization, Department Group + **ролевые даты ×3** (Order/Due/Ship Date) + **дегенеративные** Internet/Reseller/Sales Summary Order Details |
| Parent-child иерархии | 4 | **Account (+унарные операторы)**, **Organization (+унарные)**, Employee, Department |
| Пользовательские иерархии | ~19 | Date ×4 (Calendar, Fiscal, Calendar Weeks, Fiscal Weeks), Product ×3 (Categories, Model Lines, Stock Level), Customer Geography, Geography, Sales Territory, Reseller ×4, Promotions, Sales Reasons, Sales Orders ×3, Employee Department |
| MDX-скрипт | 34 расчёта | **23 calculated members** (Gross Profit/Margin %, Ratio to All/Parent Products, YoY Revenue Growth, Avg Unit Price, Revenue per Salesperson, Total Active Salespeople, Discount %…) + **11 named sets** (Top 50 Customers, Core Product Group, Long Lead Products…) |
| KPI | ~12 | (Revenue, Gross Profit, Margins, Net Income, Expenses, Total Assets, Growth in Customer Base…) — полный список извлечь на Ф9 |
| Actions | 16 | 5 drillthrough (Internet/Reseller/Finance/Sales Summary Details), City Map (URL), Sales Reason Comparisons и др. |
| Perspectives | 5 | Direct Sales, Channel Sales, Sales Summary, Finance, Sales Targets |
| Translations | 626 | es-ES (1036) + fr-FR (3082) — caption-переводы |
| Хранилище | MOLAP | партиции + aggregation designs (`Adventure Works.partitions`), proactive caching |

Ключевые структурные сложности: **many-to-many** (Sales Reason → Internet Sales/Customer,
6 вхождений), **валютная конверсия** через MDX SCOPE по Destination Currency,
**полуаддитивные меры** (ByAccount/LastNonEmpty/AverageOfChildren), **унарные операторы**
(parent-child custom rollup).

## 3. Карта миграции SSAS → Cube

Статусы: ✅ переносится, ⚠️ частично (с потерями/переделкой), ❌ не переносится.

| SSAS-концепция                                              | Cube-эквивалент                                   | Статус | Комментарий                                                                                                                                                                                                                               |
| ----------------------------------------------------------- | ------------------------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Measure group                                               | отдельный cube (или один cube + `prefix`)         | ✅      | 11 MG → 5–6 cube (см. §7)                                                                                                                                                                                                                 |
| Мера Sum/Count                                              | `measures.type: sum/count`                        | ✅      | прямое сопоставление колонок                                                                                                                                                                                                              |
| DistinctCount                                               | `type: count_distinct`                            | ✅      | Order Count, Customer Count                                                                                                                                                                                                               |
| Мера None (Unit Price %)                                    | `type: avg` / raw dimension                       | ⚠️     | в SSAS None не агрегируется; в Cube вынести как dimension или `min/max` по grain                                                                                                                                                          |
| Role-playing даты ×3                                        | алиасные joins + `cube.name` даты                 | ✅      | Cube поддерживает многократный join одной таблицы                                                                                                                                                                                         |
| Дегенеративные измерения (Order Details)                    | dimension над колонками факта                     | ✅      | SalesOrderNumber/Line как dimension                                                                                                                                                                                                       |
| Пользовательские иерархии (уровневые)                       | `hierarchies` в cube                              | ✅      | Calendar/Fiscal/Product Categories и т.п.                                                                                                                                                                                                 |
| Parent-child                                                | flatten: closure-view в DuckDB + иерархия уровней | ⚠️     | Employee/Department — ок (естественные уровни); Account/Organization — см. ниже                                                                                                                                                           |
| **Унарные операторы (Account/Organization)** | эмуляция логикой вычислений в кубе | ⚠️ | `+/-/~` из DimAccount.Operator/DImOrganization переносим в closure-view: `parent_total = Σ sign(op)·child`, где `+→1, -→-1, ~→0`; в Cube — готовые агрегаты по уровням + описание отличий (см. §4.1) |
| **Many-to-many (Sales Reason)** | bridge-view + count-меры | ⚠️ | `Sales Reason Count` ✅; суммы продаж в разрезе причины — fan-out, только через аллокацию или запрет (см. §4) |
| Calculated members (23) | меры с SQL / `views` | ⚠️ | Ratios/Avg/YoY переписываются на SQL (window functions); **семантика «на любом срезе» частично теряется** — ratio-меры считать через dividing measures (sum-numerator/sum-denominator), не avg(ratio) |
| Named sets (11) | — | ⛔ вне скоупа | исключено по решению (см. §12) |
| KPI (~12) | **метрики Cube (views, MetricFlow-семантика)** | ⚠️ | нет first-class KPI-объекта (goal/trend/icon); каждая KPI → метрика `value` + сопутствующие метрики `target`/`status_` (SQL CASE) в view |
| **Полуаддитивные ByAccount/LastNonEmpty/AverageOfChildren** | SQL-выражения с фикс. grain                       | ⚠️     | LastNonEmpty → `arg_max`-подобный подзапрос по дате; AverageOfChildren → AVG по датам; ByAccount → CASE по AccountType **на уровне детализации до агрегации** (иначе теряется). Работает на фиксированном grain, не на произвольном срезе |
| **Валютная конверсия (MDX SCOPE + Destination Currency)**   | ETL/view: мера в Pivot Currency                   | ⚠️     | пересчёт в USD на уровне факта/вьюхи (join FactCurrencyRate AverageRate на OrderDateKey); произвольный выбор валюты отчёта в рантайме — ❌                                                                                                 |
| Perspectives (5) | — | ⛔ вне скоупа | исключено по решению (см. §12) |
| Translations (es/fr) | — | ⛔ вне скоупа | исключено; у нас RU-метаданные в описаниях |
| Actions / drillthrough | — | ⛔ вне скоупа | исключено; детализация — на стороне Evidence при необходимости |
| Партиции + aggregation designs | pre-aggregations Cube / DuckDB | ⏸ отложено | объём микроскопический (<1M строк); вернуться по результатам профилирования `bench-protocol.md` |
| Proactive caching | — | ⛔ вне скоупа | статичный снапшот — неактуально |
| AMO/XMLA, Excel PivotTable (MDX) | Cube SQL API (pg-wire) / REST | ⛔ вне скоупа | исключено; потребители — ИИ-агент (MCP/REST), Evidence, SQL-клиенты |
| Роли/безопасность ячеек | access_policy + security context | ⏸ отложено | dimensional security в OSS есть (`cube-rbac.md`); cell-level — нет; возвращаемся при необходимости |

## 4. Ключевые ограничения — подробно

1. **Унарные операторы плана счетов — эмуляция вычислениями**. SSAS даёт узлам Account/
   Organization операторы `+` (включить), `-` (вычесть), `~` (игнорировать). Нативно Cube
   этого не умеет, поэтому **переносим логику в вычисления**:
   - closure-view `dim_account_flat` (recursive CTE) размножает каждый узел на пути к корню
     с кумулятивным знаком: `sign = Π sign(op)` по пути, где `+→1, -→-1, ~→0`;
   - агрегат `Account Amount` = `SUM(sign · Amount)` по flatten-уровням — воспроизводит
     унарную семантику на любом уровне иерархии;
   - `~`-узлы дают sign=0 → исключаются из родительских итогов, как в SSAS;
   - отличия от SSAS фиксируем в description куба (`aw_finance`) + контрольный тест Ф10
     (итог по корню == Amount для «Assets» с учётом знаков).
   Тот же приём — для DimOrganization. Это меняет статус с «потеря» на «перенос с переделкой».
2. **M2M Sales Reason**: `FactInternetSalesReason` — мост «заказ ⇄ причина». Count-distinct
   причин/заказов по причине — тривиально. «Выручка по причине покупки» в SSAS корректно
   аллоцируется движком; в Cube прямой join даст **дублирование выручки** (заказ с 2 причинами
   удвоится). Переносим только count-семантику; аллокацию выручки по причинам — отдельная
   view с явным правилом разбиения (например, равными долями), помеченная как «не SSAS-эквивалент».
3. **MDX-SCOPE валютная конверсия**: SSAS пересчитывает любую меру в валюту отчёта на лету.
   В Cube — один пересчитанный вариант (USD, AverageRate на дату заказа) в view
   `fact_internet_sales_usd`. Мультивалютность рантайма выпадает.
   **Решено (2026-10-31): фикс. USD как основная валюта конвертации.**
   **Уточнение при Ф5 (2026-10-31): конверсия НЕ НУЖНА** — суммы обоих фактов
   уже хранятся в USD (CurrencyKey — валюта сделки для SSAS-конверсии в другие
   pivot-валюты; сырые SUM == SSAS-тоталам при pivot USD: 29 358 677.2207 /
   80 450 596.9823). Факт-вьюхи `fact_*_usd` не строятся; решение «фикс. USD»
   выполняется тривиально. Курсы остаются справочником (aw_exchange_rates).
4. **Ratio-меры** (Ratio to All/Parent Products, Gross Profit Margin %): корректны только при
   агрегировании numerator/denominator отдельно. В Cube это делается делением мер-сумм
   (или `views` с window functions по нужному grain). Ratio-to-parent — window по иерархии
   Product (closure view), фикс. уровни.
5. **Полуаддитивные меры**: семантика SSAS («LastNonEmpty на любом срезе времени») в Cube
   требует фиксировать grain (дата × валюта для курса; дата × счёт для Amount).
6. **Excel/Pivot-совместимость**: теряется MDX-интерфейс — главный канал потребления SSAS.
   Целевой потребитель в pocketstack — ИИ-агент (MCP/REST) + Evidence + SQL-клиенты.

## 5. Источник данных: подключение aw_dw2019_ru.duckdb

- Копия: `warehouse/aw_dw2019_ru.duckdb` (read-only для Cube; writer 1.5.5 живёт в репо-источнике).
- ATTACH-стратегия (как `pocketstack.duckdb` в `cube.js`): отдельный connection к файлу,
  схема `dbo.*` — ссылки в `sql:` полных путём (`dbo."FactInternetSales"`).
- DDL-референс: `migration/ddl/aw_dw2019_schema.sql` (репо-источник) — источники имён/типов.
- Метаданные RU: `duckdb_tables().comment` / `duckdb_columns().comment` — основа для
  `title`/`description` генератора (Ф1). Ключи, grain, единицы — из `aw_metadata.tsv`
  (384 записи), при необходимости дополняем вручную.

## 6. Конвенции метаданных для ИИ-агента

- Каждый объект: `name` (ascii snake), `title` (RU, человекочитаемо), `description`
  (RU: что это, grain, единицы, ограничения, «двойной счёт возможен» и т.п.).
- Префиксы кубов фактов: `aw_internet_sales`, `aw_reseller_sales`, `aw_sales_summary`,
  `aw_sales_targets`, `aw_finance`, `aw_exchange_rates`; общие измерения: `aw_dim_*`,
  ролевые даты: `aw_date_order` / `aw_date_due` / `aw_date_ship` (алиасы).
- Меры — только `sum`/`count`/`count_distinct` агрегаты; все производные (margin, ratio,
  avg price) — либо dividing-measures, либо `views` с window functions и явным grain.
- Блок «соответствие SSAS» в description каждой перенесённой меры:
  `SSAS: [Internet Sales Amount] MG=Internet Sales` — трассировка происхождения.
- Запрещённые семантики помечаем в description: `⚠ не SSAS-эквивалент: <причина>`
  (аллокация M2M, ByAccount-итоги, унарные операторы).

## 7. Целевая архитектура

```
warehouse/aw_dw2019_ru.duckdb (read-only)
   │  + generated DuckDB-views (Ф6): dim_account_flat (с sign-колонкой унарных операторов),
   │    dim_employee_flat, dim_organization_flat, dim_department_flat,
   │    fact_*_usd, bridge_sales_reason_alloc
   ▼
packages/cube/model/
   cubes/  aw_dim_*.cube.yml (11)     — общие измерения + иерархии
           aw_internet_sales.cube.yml и т.д. (6 фактов) — меры + joins (ролевые даты ×3)
   views/  aw_sales_overview.view.yml  — витрина для Evidence/агента
           aw_kpi.view.yml             — KPI как МЕТРИКИ (value/target/status)
   ▼
Cube REST/SQL API → opencode (Cube MCP) / Evidence
```

## 8. Фазы реализации

- [x] **Ф0. Подключение источника** (0.5 д): копия БД в `warehouse/`, конфиг cube.js,
      `just serve-up`, проверка `/meta` (таблицы видны, описания читаются из duckdb_columns).
      Защитное правило: только чтение, как `pocketstack.duckdb`.
      ✅ 2026-10-31: ATTACH AS aw_dw2019_ru (READ_ONLY) на каждом коннекте
      (TimingDuckDBDriver.configureConnection, оба режима); 30 таблиц; эталоны §9 сняты;
      регресс TPC-H: /meta 200, sales.revenue отвечает.
- [x] **Ф1. Генератор моделей** (1 д): `scripts/gen_aw_cube_models.py` — из DDL +
      `aw_metadata.tsv` генерирует скелеты `aw_dim_*.cube.yml` (title/description RU,
      primary_key, types). Ручная доводка поверх скелетов. Принцип: генерим один раз,
      дальше модели живут в git (не templated data-blending).
      ✅ 2026-10-31: TDD (21 тест, packages/harness/tests/test_gen_aw_models.py);
      25 скелетов (16 Dim + 9 Fact, SKIP 5 служебных); /meta 33 куба, 0 ошибок;
      запросы aw_dim_currency/aw_internet_sales через REST подтверждают ATTACH.
- [x] **Ф2. Измерения** (1 д): 11 dim-кубов с иерархиями (Date ×4, Product ×3,
      Customer Geography, Sales Territory, Reseller ×4…), ролевые даты ×3 алиасами.
      ✅ 2026-10-31: 11 aw_dim_* (account, currency, customer+geo, date, employee,
      product+subcat/cat, promotion, reseller+geo, sales_reason, sales_territory,
      scenario) + 3 ролевых aw_date_{order,due,ship} (копии базового куба).
      Иерархии = ground truth из SSAS .dim (Customer Geography, 4×Date, 3×Product,
      Promotions, 4×Reseller, Sales Territory, Sales Reasons, Employee Department).
      Снежинки geography/subcategory денормализованы в sql кубов; ES/FR вне скоупа.
      Грабли: js-yaml не терпит «: » в plain-скалярах; Cube 1.8.13 не принимает
      description в hierarchies (тексты перенесены в description куба).
- [x] **Ф3. Факты: базовые меры** (1 д): 6 кубов, 38 SSAS-мер → sum/count/count_distinct;
      join-деревья без фан-аута (проверка: сумма SalesAmount == SQL-эталон).
      ✅ 2026-10-31: 6 кубов (internet_sales 11 мер, reseller_sales 12,
      sales_summary 11 UNION ALL + sales_channel, sales_targets, finance интерим,
      exchange_rates интерим). Верифицировано: internet 29 358 677.2207 /
      reseller 80 450 596.9823 / summary 109 809 274.2030; DC: 27 659 заказов,
      18 484 клиента; анти-фанаут: Σ по категориям == тотал (29 358 677.2207).
      ByAccount/LastNonEmpty/AverageOfChildren — интерим-меры с пометками (Ф5).
      Joins: {cube}."RawCol" плейсхолдеры (subquery-cubes), ролевые даты ×3.
      Удалены внескоуповые скелеты call_center/survey/product_inventory.
- [ ] **Ф4. Calculated members → SQL** (1–2 д): 23 меры: Gross Profit (sum-numerator /
      sum-denominator), Margin %, Avg Unit Price/Sales Amount (взвешенные), YoY Growth
      (window ym-12 — паттерн `sales_mov`), Discount %, Revenue per Salesperson.
- [x] **Ф5. Полуаддитивные + валюты** (1 д): Exchange Rates (LastNonEmpty → подзапрос
      argmax по DateKey; AverageOfChildren → AVG), fact_*_usd конверсия AverageRate,
      Financial Amount ByAccount → CASE по AccountType + предагрегированные итоги.
      ✅ 2026-10-31: УПРОЩЕНИЕ — конверсия не нужна: суммы фактов уже USD
      (CurrencyKey — валюта сделки; сырые SUM == SSAS-тоталам при pivot USD,
      §4.3 обновлён). Exchange Rates: average_rate_avg (avg, приближение
      AverageOfChildren) + last_end_of_day_rate (LastNonEmpty-эмуляция:
      скалярный argmax-подзапрос, срез по валюте; GBP 1.5533/EUR 0.9669/CAD
      0.6347 — правдоподобные AW-курсы). ByAccount → Ф6 (aw_account_flat).
- [x] **Ф6. Parent-child flatten + унарные операторы** (1–1.5 д): closure-views в DuckDB
      (recursive CTE) для Account/Employee/Organization/Department; для Account и
      Organization — sign-колонка из Operator (`+→1, -→-1, ~→0`) и мера
      `Account Amount = SUM(sign·Amount)` (эмуляция унарной семантики, §4.1);
      иерархии уровней в Cube; контроль корневых итогов.
      ✅ 2026-10-31: 4 flatten-куба (inline recursive CTE, БЕЗ записи в duckdb —
      отклонение от §7 в пользу git-версионированных моделей): aw_account_flat
      (sign-эмуляция; корень Balance Sheet = 0.000000064 — минусы сводят баланс,
      контроль §4.1 пройден; amount_leaf == ΣFactFinance 1 358 640 412.70),
      aw_employee_flat (простая свёртка; команда Stephen Y Jiang 63.3M — канон AW),
      aw_organization_flat (ВЕСОВАЯ унарная колонка: SSAS Organization operator =
      PercentageOfOwnership, вклад = доля владения; closure с Π весов),
      aw_department_flat. Меры-листья через SUM(CASE WHEN depth=0) — без фана.
- [x] **Ф7. M2M Sales Reasons** (0.5 д): count-меры + bridge-view с аллокацией (пометка
      «не SSAS-эквивалент»).
      ✅ 2026-10-31: куб aw_sales_reason (inline CTE): reason_line_count (Count),
      orders_count (DC), allocated_sales_amount (равные доли между причинами
      строки). Контроль: Σ аллокации == выручка строк с причинами
      22 430 131.5744 (строки без причин в разрез не попадают — как в SSAS M2M).
- [x] **Ф8. KPI → метрики** (1 д): извлечь полный список KPI из `.cube`; каждая KPI →
      **метрика в `aw_kpi.view.yml`**: `value` (базовая мера/SQL), сопутствующие
      `target_*` и `status_*` (SQL CASE против цели); метрики соответствуют
      MetricFlow-семантике Cube и запрашиваются агентом как единый объект.
      ✅ 2026-10-31: извлечены все 12 KPI из XML (Value/Goal/Status MDX).
      Реализовано кубом aw_kpi (long-формат: строка = KPI; product margin —
      по категории, 15 строк): колонки value/target/status (KpiValue/Goal/Status),
      пороги из MDX; финансы — Actual vs Budget с унарной свёрткой поддерева
      счёта; revenue-семейство — последний FY vs LY×1.15/1.10/квота; ROA при
      пустом бюджете = status 0 («Not Budgeted», как SSAS).
- [x] **Ф9. Верификация** (1 д): golden-queries: 15–20 контрольных агрегатов (SQL к
      duckdb напрямую == Cube REST == значения, зафиксированные в этом доке);
      анти-тест фан-аута (join не удваивает суммы); контрольный итог унарной
      эмуляции (корень Account == Σ sign·Amount); тесты в `packages/harness`
      (расширение текущих 70 passed).
      ✅ 2026-10-31: packages/harness/tests/test_aw_golden.py — 20 тестов
      (тоталы/DC-меры, фан-аут ×4 включая M2M, margin=ratio_of_sums,
      mov-Σ==109 809 274.2030, Σ долей категорий==1.0, баланс==0,
      CEO-итог==80 450 596.98, LastNonEmpty==argmax SQL, KPI↔account_flat
      консистентность). Прогон: 164 passed, 22 skipped (регрессии нет).
- [x] **Ф10. Доки и демо** (0.5 д): раздел в `README`, пример запроса агента,
      Evidence-страница «AW: SSAS vs Cube».
      ✅ 2026-10-31: README-раздел «AW: SSAS Multidimensional → Cube» (обзор,
      пример запроса); Evidence-страница /aw-ssas-vs-cube (KPI-таблица,
      выручка по годам×каналам, категории; источники aw_kpi/aw_summary_by_year/
      aw_product_categories материализуются `npm run sources`).
      Грабли Evidence: SQL API 1.8.13 не поддерживает cross-cube JOIN
      (ни явный, ни неявный) — источники переписаны на одиночные кубы
      (mov/ratios уже содержат нужные разрезы). Ещё: (1) литеральные `<...>`
      в markdown-заголовках ломают компиляцию страницы (Svelte-парсер);
      (2) `docker compose build evidence` стирает материализованные
      sources/манифест — после КАЖДОЙ пересборки образа выполнять
      `docker compose exec evidence npm run sources` (как в just rebuild).

Итого оценка: ~8–9 рабочих дней.

## 8.1. Ф11 (добавлено 2026-10-31, РЕАЛИЗОВАНО 2026-11-05): план/факт — бэклог-2 plan.md №15 на данных AW

Рескоуп: задача plan.md №15 («второй факт другой гранулярности на conformed
dims») реализуется ЗДЕСЬ на данных AW — синтетический генератор (`gen_plan.py`
из docs/fact-plan.md) не нужен, план уже есть в источнике.

| Что | AW-данные |
|---|---|
| План (грубая гранулярность) | `FactSalesQuota` → `aw_sales_targets`: сотрудник × квартал, USD (2010–2013, 163 строки) |
| Факт (детальная гранулярность) | `FactResellerSales` → `aw_reseller_sales`: строка заказа (день), только продавцы (17) |
| Conformed dims | `aw_dim_employee`, `aw_dim_date` (уровень квартала), `aw_dim_sales_territory` (через сотрудника) |

Реализация: куб `aw_quota_vs_actual` — **смешанный grain** (развитие приёма Ф3):
план-строки employee×quarter (месяц NULL, `RowKey` «q:*») UNION ALL факт-строки
employee×month (квота NULL, «a:*») — обе стороны предагрегированы в SQL куба,
анти-фанаут по построению; суррогатный `RowKey` — primary key (требование Cube
при joins). Меры: `sales_amount_quota`, `sales_amount`, `gross_profit`,
`variance`, `completion_pct` и `variance_pct` (деление сумм). Территория —
conformed через сотрудника (DimEmployee→DimSalesTerritory, не территория
сделки); `sales_territory_country` предвычислена в SQL куба, т.к. SQL API 1.8.13
не резолвит join-размерности (приём aw_summary_by_year). Срез ниже
гранулярности плана (месяц/день) — план NULL, факт есть (Г3).

Гипотезы — итоги (2026-11-05):
- Г1 ✅ паритет REF ↔ Cube без потерь/дублей: тоталы, годы, employee×quarter,
  страны (golden `TestQuotaVsActual`, 7 тестов; bench 16/16 parity);
- Г2 ✅ `completion_pct` = Σфакт/Σквота на любом срезе ≥ квартала; тест
  фиксирует, что деление сумм ≠ среднее квартальных отношений;
- Г3 ✅ срез месяцем: план NULL, факт есть; Σ месяцев квартала == факту
  квартала (REST и SQL API);
- Г4 ✅ latency сопоставима: REST p50 факт 13 мс vs план-факт 12 (кварталы) /
  15 (месяцы) мс, SQL API 58/57/56 мс — bench-прогон
  `results/runs/2026-11-05T174711` (16 вопросов, N=3);
- Г5 ⏸ RBAC — вместе с cell-security (§11).

Верификация: 7 golden-тестов `test_aw_golden.py::TestQuotaVsActual` +
3 bench-вопроса в harness.golden (`aw_fact_by_quarter_2012`,
`aw_quota_vs_actual_quarters_2012`, `aw_quota_vs_actual_months_2012_q1`;
REF-путь `{{AW_DB}}` подставляет `reference_query`). Evidence: дашборд
`/quota-vs-actual` (строки год/квартал/месяц; метрики план+факт+completion;
фильтры год × страна; данные материализованы в sources
`aw_quota_vs_actual_{kpi,quarters,months}.sql` — страничные запросы
Evidence-runtime выполняет в локальном duckdb поверх sources) + 3 блока на
`/verification`. Критерий готовности: `just verify` 141 passed — выполнен.
Вторая реализация тех же мер через blending-view и обобщение вопросов
сессии — §8.2 (дашборд `/quota-vs-actual-blend`).

## 8.2. Ф11.1 (2026-11-05): план/факт тремя способами — FAQ сессии и blending

Обобщение вопросов/рассуждений сессии 2026-11-05 вокруг Ф11 (задокументировано
по запросу пользователя).

### В1. Можно ли в Evidence показывать данные нескольких кубов, не объединяя их в один запрос?

Да. Страница Evidence = N независимых sql-блоков, каждый — свой запрос к
своему кубу. Это аналог **measure groups** SSAS Multidimensional: панели
независимы, а **conformed dimensions** эмулируются общими inputs (год, страна
в WHERE каждого запроса), **частные фильтры** — inputs только своего запроса.
Разная гранулярность отображается корректно: панель факта — месяц 100K, панель
квота — квартал 300K, и это видно. В нашем сетапе Evidence-runtime выполняет
запросы в локальном duckdb поверх **материализованных sources** — «несколько
кубов» = несколько файлов в `sources/cube/`.

### В2. А производные вычисления (факт/план) — обязательно объединять в один запрос?

Производная мера должна вычисляться там, где оба аргумента видны **в одном
контексте среза**. Три места:

| Место | Механика | Цена |
|---|---|---|
| Cube: один куб | SQL куба предагрегирует обе стороны (Ф11, mixed grain) | логика grain в SQL куба; самый контроль |
| Cube: blending view | члены двух кубов в одном view, выражение над мерами (Ф11.1) | ограничения ниже |
| BI-слой (Evidence duckdb) | JOIN двух materialized источников на странице | формула вне семантического слоя: MCP/SQL API не видят, кэш/RBAC не применяются, дублируется в каждом отчёте |

Принцип проекта: **вычисления — в Cube, страница только фильтрует** → один из
двух первых вариантов.

### В3. Как работает blending-механика Cube (на нашей 1.8.13)

View `plan_vs_fact_blend` (два факта + общие оси aw_dim_date, мера
`completion_pct` — выражение над мерами разных кубов). Сгенерированный SQL
(`/v1/sql`): **CTE на каждый куб** вида `dim LEFT JOIN факт GROUP BY ось`,
затем оси-ключи (UNION всех сторон) LEFT JOIN'ят агрегаты; `completion_pct`
вычисляется **над готовыми агрегатами** — деление сумм (анти-фанаут по
построению, аналог SSAS measure groups + calculated member). Числа идентичны
mixed-grain кубу на срезах год/квартал (golden `TestPlanVsFactBlend`, 4 теста).

### Эмпирические ограничения blending на 1.8.13 (почему основной путь Ф11 — предагрегация)

1. **`many_to_many` relationship выпилен** из схемы-компилятора (валидны
   только belongs_to/has_many/has_one) — «старый» декларативный blending
   из ранних версий Cube недоступен.
2. **Несвязанные корни не поддерживаются**: view обязан задать join_path от
   одного корня; чтобы факты не терялись, звезда строится с корнем-dim
   (рёбра dim→факт объявлены в aw_dim_date). Корень-факт терял строки:
   targets→dim LEFT JOIN факт оставлял только продажи первых дней кварталов
   (19.1M из 80.4M эталона — поймано тестом).
3. **Направление join решает**: dim-корень даёт «пустые» годы календаря
   (обе меры NULL, 2005–2014) — фильтруются на стороне потребления
   (HAVING в sources, guard в тестах).
4. **Grain оси**: квота джойнится к DateKey первого дня квартала — ось
   «месяц» ложно отнесла бы всю квартальную квоту к одному месяцу
   (в отличие от mixed-grain куба, где месяц план-строк = NULL). Поэтому
   blending-пример срезает только год/квартал; месячная детализация — пример 1.
5. **Conformed-оси ограничены схемой**: у квот нет пути к территории, кроме
   как через сотрудника → фильтра по стране в blending-примере нет.
6. **SQL API**: прямой cross-cube JOIN не поддерживается, но view доступен
   как одиночная сущность (`FROM plan_vs_fact_blend` — работает, проверено).
7. **RBAC**: RLS-проход идёт по всем кубам запроса — политика на подлежащем
   кубе резала view-запросы (`WHERE 1=0`, кейс RBAC-сессии 2026-10-27).
8. В новых версиях Cube большая часть этого закрыта (`multi_stage`-меры
   view против silent inflation, multi-fact views без общего корня,
   CTE+FULL JOIN в SQL API) — пересмотреть при миграции стека (Stage 6/№17).
9. **Country-ось недостижима при разных join-путях** (2026-11-05, доработка
   Ф11.1): территория сотрудника (квоты) и территория сделки (факт) — два
   разных пути к одному dim-кубу; при включении территории в view как оси
   Cube гонит обе стороны по одному пути — вторая сторона получает
   дубли/потери (обе попытки join_path пойманы тестами). Workaround:
   предвычисленные члены `emp_territory_country` (aw_sales_targets, через
   сотрудника — referenced dim, как SSAS) и `deal_territory_country`
   (aw_reseller_sales, по сделке — канон SSAS) + **раздельные запросы по
   сторонам** (двухпанельный режим, канон SSAS measure groups). Семантика:
   факт по стране сделки ≠ по стране сотрудника (Canada 2013: 5.18M vs
   3.89M) — пример-1 (обе стороны по сотруднику) и пример-2 (канон SSAS)
   закономерно различаются фактом по странам.
10. **Фильтры сторон не изолируются в одном запросе** (баг 1.8.13): оба
   country-фильтра протаскиваются во все key-CTE — чужой фильтр режет
   сторону через NULL-семантику LEFT JOIN (факт Canada 2012 терял строки:
   1.6M из 5.5M; тест-фиксация
   `test_territory_filters_together_lose_rows`). Одиночный фильтр стороны
   точен. Поэтому KPI план/факт вместе + completion — только без страны.
11. **Месяц-ось мельче grain стороны** (демо на дашборде): квота
   приписывается конкретному месяцу по DateKey строки квоты (источник AW
   датирован «примерно квартальными» днями: 20120331, 20110701, 20101229);
   Σ года цел, семантика сломана (тест-фиксация
   `test_month_slice_grain_distortion`; сравнение с mixed-grain кубом —
   блок «По месяцам» на /quota-vs-actual-blend).

### Матрица выбора

| Критерий | Ф11 mixed-grain куб | Ф11.1 blending view | BI-слой Evidence |
|---|---|---|---|
| Производная мера в семантике (MCP/SQL API/RBAC/кэш) | ✅ | ✅ | ❌ |
| Срез мельче grain плана (месяц) корректен | ✅ NULL | ❌ искажение | зависит от JOIN |
| Все dims обеих сторон (страна) | ✅ | только общие оси | ✅ |
| Логика grain | в SQL куба (явная) | в компиляторе (неявная) | на странице |
| Риск silent-ошибок | низкий (тесты на REF) | средний (версионные нюансы) | высокий (дубли) |

Практика проекта: mixed-grain куб (Ф11) — основной путь для plan/факт с
разными grain; blending view (Ф11.1) — демонстрация механизма и рабочий
вариант для фактов **одинаковой** гранулярности с **общими осями и общими
путями к dim**; BI-слой — только для «независимых панелей» (В1), не для
производных. Страна/месяц в план/факт — через mixed-grain куб (пример 1);
в blending — раздельные запросы по сторонам (страна) и вообще не месяц
(пример 2, ограничения 9–11).

Дашборды: пример 1 `/quota-vs-actual` (mixed grain, месяц+квартал+страна),
пример 2 `/quota-vs-actual-blend` (blending, год/квартал) — числа совпадают
на общих срезах.

## 9. Верификация

- Эталоны (SQL по duckdb, сняты при Ф0, движок 1.5.5):
  `FactInternetSales.SUM(SalesAmount) = 29 358 677.2207` (60 398 строк),
  `FactResellerSales.SUM(SalesAmount) = 80 450 596.9823` (60 855 строк),
  DistinctCount заказов, COUNT по причинам и т.д.
- Каждая ratio-мера проверяется на 2+ уровнях иерархии (total ≠ avg of children).
- Фан-аут: заказ с несколькими SalesReason не увеличивает выручку в витрине причин.

## 10. Риски / открытые вопросы

| Риск | Мера |
|---|---|
| Унарные операторы (Account/Organization) | эмуляция sign-колонкой в closure-view + контрольный тест корневых итогов (§4.1, Ф6) |
| Fan-out на M2M | count-only + аллокация с пометкой |
| Ratio-агрегация | только dividing-measures; запрет avg(ratio) |
| Формат duckdb 2.0 (CLI) портит файл | правило `plan.md`: только чтение, writer 1.5.5 |
| Объём ручной доводки descriptions | генератор Ф1 из tsv; ручная доводка только факт-мер |

Открытые вопросы — закрыты (2026-10-31):
1. **Мультивалютность рантайма vs фикс. USD → решено: фикс. USD (основная валюта)**.
   Конверсия — единственный предвычисленный вариант в USD (AverageRate на OrderDateKey,
   `fact_*_usd`, см. §4.3); выбор валюты отчёта в рантайме — вне скоупа.

## 11. Скоуп миграции — итоговые списки

**Вне скоупа (решено, не рассматриваем):** ⛔ named sets · perspectives · translations
(es/fr) · actions/drillthrough · proactive caching · AMO/XMLA · Excel PivotTable (MDX) ·
мультивалютность рантайма (решено 2026-10-31: фикс. USD).

**Отложено:** ⏸ партиции + aggregation designs (вернуться по профилированию bench-protocol) ·
роли/безопасность ячеек (cell-level; dimensional RBAC в OSS есть — при необходимости).

**Не поддерживается Cube, эмулируем вычислениями:** ⚠️ унарные операторы
Account/Organization (sign-closure, §4.1) · полуаддитивные меры (фикс. grain) ·
M2M-суммы (count-only + аллокация) · KPI (метрики views) · валютная конверсия
(предвычисленный USD).

Переносится полностью ✅: схема измерений и фактов, ролевые даты, иерархии (кроме
унарных), Sum/Count/DistinctCount-меры, дегенеративные измерения, ИИ-агентный доступ
(MCP/REST) — с RU-метаданными лучше оригинала.
