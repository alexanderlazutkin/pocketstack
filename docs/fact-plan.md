# План: синтетический план по выручке (`fact_plan`) — conformed dimensions в Cube

Реестр: docs/plan.md §9 №15 (бэклог-2). Статус: план утверждается.

## 1. Цель и проверяемые гипотезы

Цель — проверить способность Cube работать с **conformed dimensions** на разных
уровнях гранулярности в одном семантическом слое:

- **факт** (`marts.fact_sales`, grain = позиция заказа) — анализ на максимальной
  детализации (день, нация, бренд, …) — уже есть, не меняем;
- **план** (`marts.fact_plan`, grain = месяц × регион × сегмент) — синтетика;
- **план-факт** — обе задачи из одного слоя через view с data blending.

Гипотезы (что именно проверяем):

| # | Гипотеза | Чем проверяем |
|---|---|---|
| Г1 | Blending факта (день) с планом (месяц) через conformed dims не дублирует строки и не теряет стороны | паритет REF SQL ↔ Cube (шаг 4) |
| Г2 | Отношение мер разных гранулярностей (`plan_completion`) корректно на любом срезе ≥ гранулярности плана | golden-вопросы на разных срезах (шаг 4) |
| Г3 | Срез ниже гранулярности плана (день) даёт осмысленное поведение (план NULL, факт есть), а не мусор | отдельный golden-вопрос (шаг 4) |
| Г4 | Latency план-факт запросов сопоставима с факт-запросами (кэш Cube; pre-agg в проекте нет) | bench (шаг 6) |
| Г5 | RBAC (RLS по региону) работает на blended view как на обычном | RBAC-сценарий harness (шаг 4) |

## 2. Решения по дизайну (дефолты, см. §6)

| Решение | Выбор |
|---|---|
| Гранулярность плана | (year, month, customer_region, market_segment) — как в №15 |
| Мера плана | только выручка: `plan_revenue` (кол-во/штуки в план не кладём) |
| База генерации | агрегат факта `SUM(net_price)` по той же гранулярности |
| Формула | `plan = base × f(комбинация) × bias(регион)`; f ∈ [0.85, 1.15] из `crc32(key+seed)` — детерминизм без RNG; bias: AFRICA ×0.94 (план занижен → систематическое перевыполнение), AMERICA ×1.06 (недовыполнение), прочие ×1.0 — устойчивые паттерны для демо |
| Диапазон дат | весь диапазон факта (мин–макс ship_date), только комбинации, присутствующие в факте → план-факт join без пустых сторон; ~≤2100 строк (5×5×84) |
| Seed | параметр CLI (default 42), фиксируется в `pocketstack_meta` (`plan_seed`) — воспроизводимость |
| Схема хранения | `raw_plan.plan_revenue` — ОТДЕЛЬНАЯ от `raw_tpch`: пересев TPC-H (seed) план не сносит; затем sqlmesh-модель `marts.fact_plan` |
| Кубы | куб `fact_plan` (напрямую закрыт политикой, как `fact_sales`) + view `plan_vs_fact` (blending, `relationship: many_to_many` по год+месяц+регион+сегмент — паттерн Cube «Data Blending», уточнить по доке при имплементации) |
| Меры plan_vs_fact | `revenue` (факт), `plan_revenue`, `plan_completion = revenue / plan_revenue` (отношение агрегатов, format: percent) |
| Измерения plan_vs_fact | month, quarter, year, region, segment (день НЕ включаем — ниже гранулярности плана) |
| View `sales` | не трогаем: факт-детализация остаётся отдельной задачей (регрессия — существующие golden) |
| Evidence | страница «План-факт» через Cube SQL API (решение §9 №13) |

## 3. Конвейер данных

```
raw_tpch (dbgen) ──► marts.fact_sales ──┬─► [существующий путь: view sales]
                    marts.dim_customer ─┤
                                        └─► gen_plan.py (детерминированный)
                                              │  читает факт+дим, пишет
                                              ▼
                                        raw_plan.plan_revenue
                                              │  sqlmesh (kind FULL, audits)
                                              ▼
                                        marts.fact_plan
                                              │  Cube: cube fact_plan
                                              ▼
                                        view plan_vs_fact (blending с fact_sales)
```

Порядок запуска (file): `just seed` → `just apply` → `just plan-seed` → `just apply`.
`rebuild` / `rebuild-lake` получают шаг plan-seed после apply — пересборка
восстанавливает демо целиком. Lake-режим: генератор, как seed_tpch, работает
через ATTACH (WAREHOUSE_MODE=ducklake), пишет `lake.raw_plan` в транзакции каталога.

Масштабируемость: база — от факта → план автоматически масштабируется со сменой sf
(sf=1 / sf=10 без правок генератора).

## 4. Пошаговый план (TDD: RED → GREEN на каждом шаге)

### Шаг 1 — генератор `packages/sqlmesh/gen_plan.py`
- Чистая функция `build_plan(base_rows, seed, biases) -> rows` (без БД) + запись
  в duckdb (file/lake) по образцу seed_tpch.py (meta: `plan_seed`).
- Юнит-тесты `packages/sqlmesh/tests/test_gen_plan.py`: детерминизм
  (два вызова байт-в-байт), покрытие = все комбинации факта, множитель в границах,
  влияние bias, округление до цента.

### Шаг 2 — sqlmesh: `models/marts/fact_plan.sql` + рецепты
- `kind FULL`, audits: `not_null` всех ключей, `unique_combination_of_columns
  (year, month, region, segment)`; источник `raw_plan.plan_revenue`.
- Тесты (test_marts.py): гранулярность уникальна, план > 0, даты в диапазоне факта.
- Justfile: `plan-seed [seed]` / `plan-seed-lake`; шаг в `rebuild` / `rebuild-lake`.

### Шаг 3 — Cube: куб + view (skill cube-build-model)
- `fact_plan.cube.yml`: меры/измерения с русскими `title`/`description` (AI-context),
  access_policy: напрямую deny всем, кроме admin (паттерн fact_sales).
- `plan_vs_fact.view.yml`: blending fact_sales × fact_plan, меры §2.
- Проверка: MCP cube_meta/cube_load/cube_sql до коммита.

### Шаг 4 — harness: golden + parity + RBAC
- Golden-вопросы (4–6): план-факт по месяцам года; по регионам за год; выполнение
  плана сегментом по кварталам; суммарное выполнение по регионам (проверка bias);
  срез днём (Г3: план NULL); регрессия — детальный факт-вопрос через view sales.
- REF SQL: прямые запросы к duckdb marts (join fact_plan) → rows-parity с Cube.
- RBAC: user-токен региона → только свой регион в plan_vs_fact (Г5).
- `just verify` / `just verify-lake` зелёные.

### Шаг 5 — Evidence: страница «План-факт»
- Источник — Cube SQL API к view plan_vs_fact; таблица выполнение по
  месяцам×регионам, KPI-плитки (выполнение всего/AFRICA/AMERICA).

### Шаг 6 — оценка и фиксация
- Bench план-факт golden (N=3, p50) vs факт-вопросы → results/runs + results/index.md.
- Обновить: plan.md §9 №15 (статус/итог гипотез Г1–Г5), user-guide (рецепты,
  страница), README, при необходимости gotchas.

## 5. Критерии готовности

- `just test` / `verify` / `verify-lake` зелёные (существующие 141 + новые).
- Паритет REF ↔ Cube на всех новых golden.
- Демо: анализ факта на детализации (view sales) и план-факт (view plan_vs_fact)
  из одного семантического слоя, с RBAC.
- Результаты bench зафиксированы в results/.

## 6. Открытые параметры (дефолты §2 — подтвердить или править)

1. Гранулярность месяц × регион × сегмент — подтверждена в №15?
2. Шум множителя ±15% и региональные bias AFRICA −6% / AMERICA +6% — ок?
3. День не входит в разрезы plan_vs_fact (ниже гранулярности плана) — ок?
4. Seed default 42 — ок?
