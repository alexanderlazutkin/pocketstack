# План настройки и разработки демо-проекта pocketstack

Версия плана: 1.0 (2026-10-24). Обоснование выбора BI — `docs/bi-tools-comparison.md`.

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
| Семантика | Cube | 1.8.12 | REST/GraphQL + SQL API (pg-wire :15432) + MCP |
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
├── docs/                 # план, обоснования
├── packages/
│   ├── sqlmesh/          # uv-проект pocketstack-sqlmesh: seed, models, audits, tests
│   ├── harness/          # uv-проект pocketstack-harness: верификация (pytest)
│   ├── cube/             # npm: schema/, cube.ts (sqlPort 15432)
│   └── evidence/         # npm: sources, pages
├── warehouse/            # gitignored: pocketstack.duckdb
├── Justfile              # seed | plan | apply | cube | evidence | verify | demo | cli-readonly
├── pyproject.toml        # uv workspace root
└── .python-version       # 3.13
```

## 5. Стадии

### Stage 0 — Bootstrap + верификация окружения (блокирующая)
- git init, `.gitignore`, `.python-version`, обновление uv до 0.13.5
- uv-воркспейс: root + `pocketstack-sqlmesh` + `pocketstack-harness`
- Пин `duckdb==1.4.4` в обоих python-пакетах; `uv sync` — разрешение зависимостей (sqlmesh 0.236.4 совместим с 1.4.4, т.к. его диапазон `>=0.10.0,<2`)
- Justfile со всеми таргетами + guard `cli-readonly`
- **Критерий приёмки**: `uv lock` разрешается без конфликтов, `uv run python -c "import duckdb; print(duckdb.__version__)"` → 1.4.4

### Stage 1 — Данные и витрина (звезда)
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

### Stage 2 — Cube семантический слой
- npm-проект `packages/cube`, драйвер `@cubejs-backend/duckdb-driver` (node duckdb 1.4.4)
- cubes/views над mart'ами: меры (revenue, orders_count, …), измерения (region, segment, year/month)
- pre-aggregations OFF (чистый паритет SQL)
- SQL API (pg-wire) на :15432
- **Критерий приёмки**: REST-запрос и SQL-запрос через :15432 возвращают одинаковые rows

### Stage 3 — Верификационный harness (приоритет №1, TDD)
- ~12 golden-вопросов; на каждый: ожидаемый Cube-query JSON + reference SQL (из dbt-запроса пользователя)
- Проверки:
  - (a) rows-паритет: `/v1/load` vs reference SQL vs SQL API (pg-wire)
  - (b) детерминизм SQL: `POST /v1/sql` → нормализация → хэш, N прогонов
  - (c) ground truth: `SET log_query_path` в DuckDB — реальные запросы к БД совпадают с `/v1/sql`
- Артефакт: markdown-отчёт прогона (вопрос → rows ✅ / SQL-hash ✅)
- opencode: Cube MCP в `opencode.json`, демо-сценарий «вопрос → ответ → сверка с harness»
- **Критерий приёмки**: `just verify` зелёный, отчёт воспроизводим

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
| Официальный Cube MCP-пакет не найден в npm (404 на `@cubejs-backend/mcp`) | Stage 3: спайк; fallback — REST/SQL API (harness от него не зависит) |
| Смешение версий DuckDB (системный CLI 2.0 vs venv 1.4.4) | guard `cli-readonly`, всё воспроизводимо скриптами |
| Evidence 40.x — крупный скачок; bundled DuckDB неизвестен | проверка при Stage 4 (модель читает marts через `type: duckdb` только для отладки) |
| pg-wire SQL API Cube — подмножество SQL | сложную логику держим в sqlmesh/Cube, BI только фильтрует/агрегирует |

## 7. Управление

- Трекинг стадий: hive beads (эпик pocketstack + по бусине на стадию)
- TDD: тесты до реализации для каждой функциональной части
- Коммит-дисциплина: чекпоинты после каждой стадии, `warehouse/` вне git
