# План настройки и разработки демо-проекта pocketstack

Версия плана: 1.1 (2026-10-25). Обоснование выбора BI — `docs/bi-tools-comparison.md`.
Нюансы и грабли — `docs/gotchas.md`; протокол оценки запросов — `docs/bench-protocol.md`.

## 1. Цели и приоритеты

1. **Приоритет №1 — AI-агент поверх семантического слоя**: запросы к TPC-H (DuckDB) через cube.dev
   с верификацией, что разные пути формируют **одинаковые результаты** и **одинаковые SQL-запросы к БД**.
2. **Приоритет №2 — демо BI-отчётов** (Evidence поверх Cube).

## 2. Согласованный стек (пины)

| Слой | Технология | Версия/пин | Примечание |
|---|---|---|---|
| Менеджер пакетов | uv | 0.13.5 (обновить с 0.11.24) | воркспейс, единый lock |
| Python | CPython (uv-managed) | 3.13 (`.python-version`) | fallback 3.12 при отсутствии wheels |
| Хранилище | DuckDB | **==1.4.4 в venv (python + node)** | системный CLI 2.0.0 не трогаем |
| Генерация данных | `tpch` extension | core ext, `CALL dbgen(sf=N)` | детерминированный сид, sf параметризован |
| Трансформации | sqlmesh | 0.236.4 (fallback dbt-core 1.12.6) | пин `duckdb<2` в sqlmesh |
| Семантика | Cube | 1.8.13 | REST/GraphQL + SQL API (pg-wire :15432); MCP-пакета в npm нет (404) |
| AI-агент | opencode + Cube MCP + python-harness | — | запасной интерактив: Claude Code (Stage 5) |
| BI | Evidence | 40.1.8 | коннекторы `type: cube` + `type: duckdb` |
| Lakehouse (конец) | ducklake ~0.3.x + MinIO (опц.) | extension | Stage 7 |

### Защитные правила

- **Системный DuckDB CLI 2.0** к файлам проекта — только `duckdb -readonly warehouse/pocketstack.duckdb`
  (таргет `just cli-readonly`). Запись/чекпойнт 2.0 поднимет версию формата → файл станет нечитаем для 1.4.4.
- `warehouse/*.duckdb` не в git: полностью воспроизводим из `just seed` + `sqlmesh run` (дешёвый откат).
- Версия DuckDB в venv — единая 1.4.4; любые повышения — только через Stage 6.

## 3. Архитектура

```
tpch dbgen(sf=1) → [raw_tpch] → sqlmesh → staging → marts (звезда)
                                                      │
                                        ┌─────────────┤ (read-only)
                                        ▼             ▼
                                  Cube (semantic)   harness (reference SQL)
                                 /    |      \          │
                          REST/GraphQL│      MCP      сравление: rows, SQL-хэши
                                    SQL API  ▲          ▲
                                    :15432   │          │
                                        ▼    │       pytest-отчёт (артефакт)
                                    Evidence ┘ + opencode (живое демо)
```

## 4. Структура репозитория

```
pocketstack/
├── docs/                 # план, обоснования, gotchas, bench-протокол
├── packages/
│   ├── sqlmesh/          # uv-проект pocketstack-sqlmesh: seed, models, audits, tests
│   ├── harness/          # uv-проект pocketstack-harness: верификация (pytest) + bench
│   ├── cube/             # npm: schema/, cube.ts (sqlPort 15432)
│   └── evidence/         # npm: sources, pages
├── results/              # ЛОГ оценок (в git): queries/, runs/<ts>/, index.md
├── artifacts/            # verify-report.md (в git), duckdb_query_log.csv (gitignored)
├── warehouse/            # gitignored: pocketstack.duckdb
├── Justfile              # seed | plan | apply | cube | verify | bench | demo | cli-readonly
├── pyproject.toml        # uv workspace root
└── .python-version       # 3.13
```

## 5. Стадии

> Статус: ✅ выполнено (дата, commit). Нумерация X.Y — дополнения вне исходного плана,
> вписаны по порядку реализации (см. §8).

### Stage 0 — Bootstrap + верификация окружения (блокирующая) — ✅ 2026-10-25
- git init, `.gitignore`, `.python-version`, обновление uv до 0.13.5
- uv-воркспейс: root + `pocketstack-sqlmesh` + `pocketstack-harness`
- Пин `duckdb==1.4.4` в обоих python-пакетах; `uv sync` — разрешение зависимостей (sqlmesh 0.236.4 совместим с 1.4.4, т.к. его диапазон `>=0.10.0,<2`)
- Justfile со всеми таргетами + guard `cli-readonly`
- **Критерий приёмки**: `uv lock` разрешается без конфликтов, `uv run python -c "import duckdb; print(duckdb.__version__)"` → 1.4.4

### Stage 1 — Данные и витрина (звезда) — ✅ 2026-10-25 (1a/1b)
- **1.a (вход — блокирующий, от пользователя после успешной генерации TPC-H):**
  SQL dbt-модели звезды → конвертация и адаптация под sqlmesh:
  - `{{ ref('x') }}` / `{{ source(...) }}` → ссылки моделей sqlmesh / SQL-источники `raw_tpch.*`
  - материализации dbt → `MODEL_KIND` (FULL/VIEW)
  - dbt-тесты → sqlmesh **audits** (not_null, unique_key, …)
  - согласование сконвертированных моделей с пользователем до `sqlmesh run`
- **1.b TPC-H**: TDD — тест rowcount'ов 8 таблиц (RED) → `dbgen(sf=1)` в схему `raw_tpch` → GREEN
- Ожидаемые counts (sf=1): region 5, nation 25, supplier 10 000, customer 150 000,
  part 200 000, partsupp 800 000, orders 1 500 000, lineitem 6 001 215
- **Критерий приёмки**: тесты зелёные; исходный dbt-запрос пользователя зафиксирован как reference SQL для Stage 3

### Stage 2 — Cube семантический слой — ✅ 2026-10-25
- npm-проект `packages/cube`, драйвер `@cubejs-backend/duckdb-driver` (node duckdb 1.4.4)
- cubes/views над mart'ами: меры (revenue, orders_count, …), измерения (region, segment, year/month)
- pre-aggregations OFF (чистый паритет SQL)
- SQL API (pg-wire) на :15432
- **Критерий приёмки**: REST-запрос и SQL-запрос через :15432 возвращают одинаковые rows

### Stage 2.1 — Calendar-измерение (дополнение, вне исходного плана) — ✅ 2026-10-25
- Запрос пользователя: измерение календарь (Year/Quarter/Month/Day) по union-диапазону
  ship_date/receipt_date факта
- sqlmesh-модель `marts.dim_date`: 2557 дней (1992-01-02..1998-12-31), grain=день, без пропусков;
  TDD 9 тестов (`test_dim_date.py`), suite 38/38
- Куб `dim_date` + джойн `fact_sales.ship_date` (роль shipping calendar) + члены
  `sales.year|quarter|month|day|date_day` во view
- Паритет REST vs DuckDB по `revenue by year` — OK

### Stage 3 — Верификационный harness (приоритет №1, TDD) — ✅ 2026-10-25
- ~12 golden-вопросов; на каждый: ожидаемый Cube-query JSON + reference SQL (из dbt-запроса пользователя)
- Проверки:
  - (a) rows-паритет: `/v1/load` vs reference SQL vs SQL API (pg-wire)
  - (b) детерминизм SQL: `POST /v1/sql` → нормализация → хэш, N прогонов
  - (c) ground truth: `SET log_query_path` в DuckDB — реальные запросы к БД совпадают с `/v1/sql`
- Артефакт: markdown-отчёт прогона (вопрос → rows ✅ / SQL-hash ✅)
- opencode: Cube MCP в `opencode.json`, демо-сценарий «вопрос → ответ → сверка с harness»
- **Критерий приёмки**: `just verify` зелёный, отчёт воспроизводим

### Stage 3.1 — Living doc нюансов (дополнение) — ✅ 2026-10-25
- `docs/gotchas.md`: 20+ нюансов «симптом → причина → решение» (DuckDB-блокировки/версии,
  Cube views/initSql/SQL API-агрегаты/кэш, TPC-H-инварианты, окружение). Пополняется по ходу.

### Stage 3.2 — Протокол и лог оценки запросов (дополнение) — ✅ 2026-10-25
- `docs/bench-protocol.md` — методика: 3 пути (REST renew / SQL API / REF), N=3, p50/min, паритет
- `just bench` → лог в `results/` (в git, накапливается):
  `queries/<id>.sql` (SQL от Cube) · `runs/<ts>/detail.csv` (вопрос×путь×итерация)
  · `runs/<ts>/summary.{csv,md}` (сводные) · `index.md` (журнал прогонов)
- Базовый ориентир sf=1: REST 6–10 мс, SQL API ~50 мс (накладные pg-wire), REF 3–40 мс

### Stage 4 — Evidence BI
- `npm create evidence@latest` в `packages/evidence`
- `connection.yaml`: `cube` (:15432) + `duckdb_local` (read-only)
- 3–4 дашборда: выручка по регионам/сегментам, топ-клиенты, shipping performance
- **Критерий приёмки**: дашборды собираются из Cube, метрики совпадают с harness

### Stage 5 — Claude Code MCP (запасной интерактив)
- Тот же Cube MCP в Claude Code; сценарий как для opencode

### Stage 6 — Попытка миграции на DuckDB 2.0
- Условия готовности: npm-биндинги `duckdb` ≥2.0 + bump `@cubejs-backend/duckdb-driver` +
  sqlmesh снимает `<2` + расширения tpch/ducklake под 2.0 (ежемесячный upgrade watch)
- Процедура: поднять пины → перегенерировать warehouse с нуля → прогон harness + Evidence
- Провал → откат к 1.4.4 + перегенерация (дёшево: всё скриптовано)

### Stage 7 — ducklake + MinIO (последняя)
- ATTACH ducklake-каталога: сначала local FS (Parquet), опционально MinIO (docker)
- Перенастройка sqlmesh/Cube/Evidence без изменения семантики
- Параллельно: рост sf (10, …) и повторный прогон harness

## 6. Риски

| Риск | Митигция |
|---|---|
| Официальный Cube MCP-пакет не найден в npm (404 на `@cubejs-backend/mcp`) | **Реализовался** (Stage 3): fallback REST/SQL API принят; harness от MCP не зависит |
| Смешение версий DuckDB (системный CLI 2.0 vs venv 1.4.4) | guard `cli-readonly`, всё воспроизводимо скриптами |
| Evidence 40.x — крупный скачок; bundled DuckDB неизвестен | проверка при Stage 4 (модель читает marts через `type: duckdb` только для отладки) |
| pg-wire SQL API Cube — подмножество SQL | сложную логику держим в sqlmesh/Cube, BI только фильтрует/агрегирует |

## 7. Управление

- Трекинг стадий: hive beads (эпик pocketstack + по бусине на стадию)
- TDD: тесты до реализации для каждой функциональной части
- Коммит-дисциплина: чекпоинты после каждой стадии, `warehouse/` вне git
- Оценка запросов: каждый meaningful-прогон — `just bench` + коммит результатов в `results/`

## 8. Выполненные дополнения вне исходного плана (хронология)

| # | Дата | Дополнение | Где |
|---|---|---|---|
| 1 | 2026-10-25 | Calendar-измерение `dim_date` (sqlmesh + Cube + view) | Stage 2.1 |
| 2 | 2026-10-25 | `docs/gotchas.md` — living doc нюансов | Stage 3.1 |
| 3 | 2026-10-25 | Протокол оценки запросов + лог `results/` (`just bench`) | Stage 3.2 |
| 4 | 2026-10-25 | `just` установлен через `uv tool install rust-just` | окружение |
