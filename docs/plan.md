# План настройки и разработки демо-проекта pocketstack

Версия плана: 1.1 (2026-10-25). Обоснование выбора BI — `docs/bi-tools-comparison.md`.
Нюансы и грабли — `docs/gotchas.md`; протокол оценки запросов — `docs/bench-protocol.md`;
установка Evidence с нуля — `docs/evidence-setup.md`; SQL-клиенты к Cube — `docs/cube-sql-clients.md`.

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

### Stage 4 — Evidence BI — ✅ 2026-10-26
- `npm create evidence@latest` в `packages/evidence` — **сломан** (404/нет bin); развёрнут
  legacy-шаблон `github.com/evidence-dev/template` (ветка LEGACY), Evidence 40.1.8,
  `npm ci --legacy-peer-deps`; dev требует Node 20 (локально `~/.local/opt/node-v20…`)
- `connection.yaml`: `cube` (:15432) + `duckdb_local` (read-only)
- Архитектура: инлайн-запросы страниц исполняются в DuckDB-WASM поверх parquet,
  материализованных из Cube (`npx evidence sources`, `sources/cube/*.sql` = golden-SQL
  дословно) — 22 таблицы; к живому Cube BI не ходит в рантайме
- 6 страниц: index, revenue (регионы/сегменты), revenue-mov (YoY/PoP отклонения,
  год-дропдаун), top-clients, shipping, verification (13 golden-вопросов с «Назначением»)
- Отклонения YoY/PoP считаются в Cube (куб `sales_mov`, CTE+self-join; KPI-агрегаты —
  measures `abs_yoy_sum`/`rel_yoy_avg`); `days_in_transit` в факте (TDD, 39/39)
- **Критерий приёмки**: ✅ метрики дашбордов = harness (sources = golden-SQL дословно,
  паритет по построению; Σ выручки на /verification = KPI /revenue = 218,102,223,885.00;
  все 6 страниц рендерятся без ошибок консоли — `scripts/visual-check.mjs`)

### Stage 5 — Claude Code MCP (запасной интерактив) — ✅ 2026-10-26
- Официального MCP у OSS-Cube нет (`@cubejs-backend/mcp` — 404; `/mcp` — только
  Enterprise/Cube Cloud, к локальному кубу неприменим)
- Реализован свой тонкий MCP-сервер `packages/mcp` (FastMCP из mcp SDK v1,
  stdio): tools `cube_meta` / `cube_load` (renewQuery, мимо кэша) / `cube_sql`
  (ground-truth стиль) / `sql_api` (read-only whitelist через pg-wire)
- Креды из `.env`; агент работает теми же путями, что проверяет harness
- **Критерий приёмки**: ✅ MCP-клиент подключается, инструменты отвечают
  (e2e-тест stdio: list_tools + call_tool; 9/9; docs/cube-mcp.md)

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
| 5 | 2026-10-26 | `days_in_transit` в `marts.fact_sales` (TDD: контракт+sanity, 39/39) — AVG(дата−дата) в Cube SQL API не работает (interval) | Stage 4 |
| 6 | 2026-10-26 | Куб `sales_mov`: YoY/PoP отклонения (абс.+отн.) в семантическом слое, golden q13 | Stage 4 |
| 7 | 2026-10-26 | Evidence-дашборды (6 страниц) + верификационная страница с cross-ссылками на harness-отчёты; Evidence-колонки в verify-report/bench-summary | Stage 4 |
| 8 | 2026-10-26 | KPI-агрегаты года как measures куба (`abs_yoy_sum`, `rel_yoy_avg`) — метрики в Cube, BI только показывает | Stage 4 |
| 9 | 2026-10-26 | Фикс PoP января: сдвиг месяца по непрерывному индексу `ym=год*12+месяц` (было `month-1` → 0 вместо 12); эталон q13 переписан первым (RED), куб догнан (GREEN 69/69); bench 13/13, прогон `2026-10-26T133737` | Stage 4 |
| 10 | 2026-10-26 | Параметризация sf (Justfile `seed/reset sf=…`, default 1) + `scripts/stack.sh` (up/down/status/restart/sources/rebuild) — транзакционный rebuild: rename бэкап → dbgen(sf) → sqlmesh → up → sources → rm бэкап, при сбое авто-восстановление | инфраструктура |
| 11 | 2026-10-26 | README.md проекта + docs/user-guide.md (установка/запуск, разблокировка DuckDB, сценарий сверки Cube UI + Evidence, карта отчётов/логов) | документация |
| 12 | 2026-10-26 | Лог запросов DuckDB с таймингами: обёртка драйвера `TimingDuckDBDriver` (cube.js) пишет `started_at,finished_at,duration_ms,status,sql`; TDD — тест ground truth расширен ассертом таймингов (RED→GREEN 69/69); механика 3 уровней доказательств — в user-guide | Stage 3.3 |
| 13 | 2026-10-26 | Security: секреты вынесены в `.env` (шаблон `.env.example`), фолбэки-креды удалены из cube.js/harness/connection.yaml; Evidence-connection.yaml рендерится из .env (legacy не интерполирует `${VAR}`); единые имена `CUBESQL_USER/CUBESQL_PASSWORD`; .env и connection.yaml — вне git | security |
| 14 | 2026-10-26 | Stage 5: собственный MCP-сервер `packages/mcp` (FastMCP/mcp SDK v1, stdio) вокруг Cube REST + SQL API — официального пакета нет; tools meta/load/sql/sql_api; e2e-тест настоящим stdio-клиентом; фикс сборки pocketstack-harness (hatchling, пакет `harness` не устанавливался) | Stage 5 |

## 9. Реестр вопросов: статус и дата решения

| # | Вопрос | Статус | Дата | Где |
|---|---|---|---|---|
| 1 | Параметр sf при развёртывании/пересоздании БД TPC-H (default 1) | ✅ решён | 2026-10-26 | `just seed/reset sf=…`, `scripts/stack.sh rebuild [SF]` |
| 2 | Минимизация развёртывания и воспроизведения (скрипт) | ✅ решён | 2026-10-26 | `scripts/stack.sh` (+ README «Быстрый старт») |
| 3 | Статусы вопросов и даты — в файле плана | ✅ решён | 2026-10-26 | этот раздел (§9) + статусы стадий §5 |
| 4 | README проекта (цели, описание, архитектура) | ✅ решён | 2026-10-26 | `README.md` |
| 5 | Руководство пользователя: установка/запуск, разблокировка DuckDB, сценарий сверки (Cube UI + Evidence), логи тестов/оценки | ✅ решён | 2026-10-26 | `docs/user-guide.md` |
| 6 | Подключение SQL-клиентов (DBeaver/DBX) к Cube | ✅ решён | 2026-10-26 | `docs/cube-sql-clients.md` |
| 7 | PoP января: сдвиг месяца на границе года | ✅ решён | 2026-10-26 | куб `sales_mov`, эталон q13 (см. §8 п.9) |
| 8 | Security: секреты в коде → `.env` (`.env.example`), best practices | ✅ решён | 2026-10-26 | cube.js/harness/connection.yaml; README «Безопасность»; см. §8 п.13 |
| 9 | MCP для cube.dev: Enterprise/Cube Cloud недоступны для демо → свой тонкий сервер | ✅ решён | 2026-10-26 | `packages/mcp`, `docs/cube-mcp.md`; см. §8 п.14 |
