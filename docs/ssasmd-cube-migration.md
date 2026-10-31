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
