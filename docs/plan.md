# План настройки и разработки демо-проекта pocketstack

Версия плана: 1.2 (2026-10-28). Обоснование выбора BI — `docs/bi-tools-comparison.md`.
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
| Хранилище | DuckDB | **==1.5.5: python-пин + node `@duckdb/node-api` 1.5.5** | системный CLI 2.0.0 не трогаем |
| Генерация данных | `tpch` extension | core ext, `CALL dbgen(sf=N)` | детерминированный сид, sf параметризован |
| Трансформации | sqlmesh | 0.236.4 (fallback dbt-core 1.12.6) | пин `duckdb<2` в sqlmesh |
| Семантика | Cube | 1.8.13 | REST/GraphQL + SQL API (pg-wire :15432); MCP-пакета в npm нет (404) |
| AI-агент | opencode + Cube MCP + python-harness | — | запасной интерактив: Claude Code (Stage 5) |
| BI | Evidence | 40.1.8 | коннекторы `type: cube` + `type: duckdb` |
| Lakehouse (конец) | ducklake ~0.3.x + MinIO (опц.) | extension | Stage 7 |

### Защитные правила

- **Системный DuckDB CLI 2.0** к файлам проекта — только `duckdb -readonly warehouse/pocketstack.duckdb`
  (таргет `just cli-readonly`). Запись/чекпойнт 2.0 поднимет версию формата → файл станет нечитаем для 1.5.5.
- `warehouse/*.duckdb` не в git: полностью воспроизводим из `just seed` + `sqlmesh run` (дешёвый откат).
- Версия DuckDB в venv — единая 1.5.5 (выравнена с node-драйвером 2026-10-28, см. Stage 6); повышения — только через Stage 6.

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

### Stage 6 — Попытка миграции на DuckDB 2.0 — ⏸ watch 2026-10-26: не готова
- Условия готовности: npm-биндинги `duckdb` ≥2.0 + bump `@cubejs-backend/duckdb-driver` +
  sqlmesh снимает `<2` + расширения tpch/ducklake под 2.0 (ежемесячный upgrade watch)
- Процедура: поднять пины → перегенерировать warehouse с нуля → прогон harness + Evidence
- Провал → откат к 1.4.4 + перегенерация (дёшево: всё скриптовано)
- **Watch 2026-10-26 — не готова, миграция не начиналась** (пины 1.4.4 нетронуты):
  - ✅ PyPI `duckdb` 2.0.0 стабильна; расширения `tpch`/`ducklake` под 2.0 ставятся и грузятся
  - ❌ npm `duckdb` latest 1.4.4 (2.x не публикуется) — блокер Cube
  - ❌ `@cubejs-backend/duckdb-driver` 1.8.13 (наш пин актуален, bump нет)
  - ❌ Evidence: `@evidence-dev/duckdb` → `@duckdb/node-api ^1.4.2`
  - ❌ sqlmesh 0.236.4: `duckdb<2` не снят
  - Жёсткая связка подтверждена эмпирически: файл БД 2.0 (формат v999) не читается
    движком 1.4.4 («can only read versions between 64 and 67») → мигрировать можно
    только всем стеком одномоментно; python-часть в одиночку поднять нельзя
- Следующий watch: ~2026-11 (или по release-notes cube duckdb-driver / sqlmesh)
- **Update 2026-10-28 — python выровнен на 1.5.5 (prerequisite Stage 7/ducklake), пины 1.4.4 сняты**:
  - Факт: `@cubejs-backend/duckdb-driver` 1.8.13 → `@duckdb/node-api 1.5.5-r.5` (движок
    v1.5.5, замер `SELECT version()`) — стек уже был смешанным 1.4.4+1.5.5 и работал
    только за счёт обратной совместимости формата файлов (1.5.5 читает v64–68)
  - Матрица ducklake: python 1.4.4 создаёт каталог **v0.3**, node 1.5.5 требует **v1.0** —
    несовместимо в обе стороны на любом типе каталога (файл и postgres); AUTOMATIC_MIGRATION
    односторонняя и разрушает доступ старому клиенту → смешанный стек на ducklake невозможен
  - Сделано: `duckdb==1.5.5` в обоих python-пакетах (+ build-system hatchling для
    pocketstack-sqlmesh: setuptools flat-layout падал на `logs/`); выравненная пара
    1.5.5↔1.5.5 на pg-каталоге полностью интероперабельна (чтение/чередование записи/
    кросс-запись/READ_ONLY)
  - Верификация: `just verify` — 88 passed / 1 skipped (prod-Cube, RBAC включён)
  - Миграция на 2.0 по-прежнему ⏸: CLI 2.0 пишет v999, нечитаемо и для 1.5.5

### Stage 7 — ducklake (pg-каталог + MinIO) + контейнеризация serving-слоя — ✅ закрыта 2026-10-29 (UAT пройден)

Цель: опция развёртывания витрины как DuckLake (каталог PostgreSQL, parquet в MinIO)
поверх выравненного стека 1.5.5; serving-слой (cube+evidence) — в контейнерах (вариант A).

**Принятые решения (2026-10-28, реестр §9 №10–14):**
- **Два режима**: файловый `warehouse/*.duckdb` — основной (демо); ducklake — опция
  для тренировок. Переключатель окружением (`WAREHOUSE_MODE=file|ducklake`);
  бенчи «до/после» — в двух режимах отдельно, цифры не смешиваются.
- **Time-travel снапшоты** ducklake храним (анализ через `ducklake_snapshots()`),
  но обязателен механизм чистки (шаг 8): снапшот-expiry + `mc rm` сирот.
- **Evidence** — только через Cube SQL API (pg-wire); прямой `type: duckdb`-коннектор
  к lake не подключаем (иначе 4-й клиент lake с собственными `SET s3_*`).
- Каталог — PostgreSQL 17, данные — MinIO (docker compose). URL файлов единые
  `s3://bucket/...`; endpoint/creds — per-session (хост `localhost:9000`,
  контейнеры `minio:9000` — два значения одной переменной, не смешивать).
- Cube аттачит lake **READ_ONLY** — защита от случайной AUTOMATIC_MIGRATION каталога.

Prerequisite выполнен (2026-10-28): матрица совместимости + бамп duckdb 1.5.5 —
см. Stage 6 Update 2026-10-28; каталог v1.0, все движки на одной версии.

**Дорожная карта:**

| # | Шаг | Критерий приёмки | Статус |
|---|---|---|---|
| 1 | compose-скелет: postgres+minio+mc-init (healthchecks, порты 127.0.0.1, секреты из .env) | `docker compose up -d --wait` → pg ready + бакет существует | ✅ 2026-10-28 (minio = `elestio/minio` по digest: официальный бинарник + mc; `minio/minio` удалён с Hub) |
| 2 | S3-пробы обоих движков: `SET s3_url_style='path'`, `s3_use_ssl=false`, endpoint хост/контейнер | python и node пишут/читают parquet в MinIO через pg-каталог; кросс-доступ | ✅ 2026-10-28 (интероп py↔node через S3: 6→7 строк, снапшоты 4→5; чистка drop+mc rm проверена) |
| 3 | seed → lake: dbgen локально → CTAS в `lake.raw_tpch` (транзит через диск); маркер sf; тесты counts sf-aware (целые sf — линейно, дробные — skip) | counts = sf-эталон; parquet в бакете; тесты зелёные при любом целом sf | ✅ 2026-10-28 (`WAREHOUSE_MODE`; маркер `pocketstack_meta` в обоих режимах; тесты sf-aware: 136 passed на sf=10; lineitem/fact_sales — допуск 0.1%, счётчик dbgen нелинеен; lake-тест `RUN_LAKE_TESTS=1` идемпотентен) |
| 4 | sqlmesh на lake: `attach:` в gateway-конфиге, модели в схему lake, state — локальный .duckdb | `plan --auto-apply` строит звезду; повторный ран идемпотентен | ✅ 2026-10-28 (gateway `lake`: `catalogs.lake` type ducklake + env_var-секреты; state в `warehouse/lake_state.duckdb`; lake — каталог по умолчанию: физика `sqlmesh__marts`, прод-view `marts`; тест `RUN_LAKE_TESTS=1` — сборка + идемпотентность; file-режим не задет: «No changes to plan») |
| 5 | Cube на lake: per-connection ATTACH + SET s3_* + READ_ONLY (обёртка TimingDuckDBDriver) | `just cube` отвечает; стресс 20+ конкурентных запросов без плавающих ошибок пула | ✅ 2026-10-28 (`configureConnection`-override: LOAD/INSTALL расширений → SET s3_* → ATTACH **AS pocketstack** (логическое имя каталога из модели) READ_ONLY → USE; стресс `scripts/cube_stress.py` 40×40: все 200, data идентичны; orders_count из lake = 1 500 000 (sf=1 канон); file-регресс: 15 000 000 (sf=10)) |
| 6 | harness: ground-truth путь через attach (env-параметризация) | `just verify` 88/88 в ducklake-режиме | ✅ 2026-10-28 (`harness/warehouse.py`: file — read-only файл, ducklake — ATTACH READ_ONLY **AS pocketstack** (логическое имя, как в модели Cube и референс-SQL) + USE; коннект-фабрика общая для conftest-фикстуры и bench; `just verify-lake` / `bench-lake`; приёмка: verify-lake **88/1**, регресс file verify **88/1**) |
| 7 | Вариант A: cube+evidence контейнеры (node:20-bookworm, расширения в образе, рендер connection.yaml в entrypoint) | стек целиком через compose; MCP на хосте без изменений | ✅ 2026-10-28 (`docker/cube` node:**24**-bookworm (cubejs-server требует Node≥22; пин 20.19 — только Evidence), `docker/evidence` node:20.19.0 + entrypoint-рендер connection.yaml; профиль `serve`; bind: warehouse + artifacts (query-log ground truth); секреты env_file; `just serve-up/serve-down/cube-stop`; приёмка: dev 70/19 (RBAC-гвард), **прод 88/1**, Evidence 200, ducklake-контейнер 1 500 000) |
| 7.1 | Зачистка хостового serving-окружения после перехода на контейнеры: Node 20 в ~/.local/opt (нужен был только Evidence), хостовые запуски cube/evidence (stack.sh host-ветка), лаунчеры /tmp; в Desktop-VM — только pocketstack-мусор (старые сборки), чужие образы (ragflow и пр.) НЕ трогаем; на хосте остаются pipeline (uv), harness, MCP | доки/скрипты не требуют хостового serving; disk freed | ✅ 2026-10-29 (Node 20 удалён −169 МБ; /tmp-лаунчеры уже отсутствуют; Desktop-VM: pocketstack-мусора нет — единственный dangling чужой (2026-08-19), образы pocketstack актуальны; Justfile `evidence`→контейнер, user-guide/gotchas/evidence-setup — контейнер-первичны; stack.sh host-ветка осознанно ждёт шага 9; бонус-грабля: порт 9000 занят snap lemonade-server → S3 на 9002, docs/gotchas.md «Окружение») |
| 8 | rebuild + чистка: сброс state sqlmesh, DROP/пересоздание lake-данных, снапшот-expiry (`--prune-old`), `mc rm` сирот; обе ветки WAREHOUSE_MODE по процедуре «Смена sf» | повторный rebuild не раздувает бакет; смена sf в ducklake без даунтайма куба | ✅ 2026-10-29 (`--prune-old` в seed_tpch: expire→cleanup→orphan-scan — НОСИТЕЛЬНО через ducklake-функции, mc не нужен (orphan-scan листит корень бакета — на MinIO/path-style 404, best-effort с варнинговом); prune-only `--prune-old` без sf — финальный шаг `just rebuild-lake SF` (после apply — снапшоты растут и от sqlmesh); Justfile `rebuild` (file, контейнерный: cube-stop→seed→apply→serve-up→sources В КОНТЕЙНЕРЕ) и `rebuild-lake`; тесты: unit CLI 5 + lake prune 1 (снапшоты→1, объекты стабильны, mc-подсчёт реальный); приёмка: lake zero-downtime свап 1.5M→15M при живом кубе (RestartCount=0; «старое» число = кэш Cube, обходится renewQuery — грабля в gotchas), повторные rebuild бакет 36→36 объектов, verify-lake **88/1** на sf=10; file: rebuild 10 → sources в контейнере (debug-источник duckdb_local отключён в entrypoint) → verify **88/1**) |
| 8.1 | bench + доки: два режима в bench-protocol (`just bench` / `bench-lake`), user-guide §ducklake (serve-up, смена режима, sf-процедура), финальные статусы Stage 7 | цифры зафиксированы в обоих режимах, доки сходятся с реальностью | ✅ 2026-10-29 (bench-protocol v1.1 §1a два режима + актуальные ориентиры sf=10: file 127/392/1300, ducklake 112/215/1742 мс Σp50, паритет 13/13 в обоих, прогоны 2026-10-29T214643/214719; user-guide §3a ducklake: serve-up, seed/apply, rebuild-lake, кэш/renewQuery, time-travel-опция; gotchas: кэш Cube после свапа, orphan-scan 404 MinIO, mc-грабли) |
| 9 | **Review проекта и документации**: ревизия всего changeset Stage 7 (бамп 1.5.5 + ducklake + контейнеры) как целого — код/тесты/конфиги; сверка каждой доки с реальностью (README быстрый старт с compose, user-guide, gotchas, bench-protocol, cube-rbac: прод в контейнере); судьба `scripts/stack.sh` после контейнеризации serving (host-ветка up/down устарела → pipeline-only или deprecate); мёртвые ссылки/упоминания | каждая команда из доков воспроизводима end-to-end; ревью-чеклист закрыт; workspace чистый (всё закоммичено) | ✅ 2026-10-29 (п.2 доки + п.3 stack.sh + 9.1 реестр — см. хронология №18–20; end-to-end воспроизводимость подтверждена пользователем в UAT — шаг 10) |
| 9.1 | **Аудит отклонений от оригинальных релизов компонентов**: для каждого стороннего компонента (Cube backend + @cubejs-backend/duckdb-driver, sqlmesh, duckdb + расширения tpch/ducklake/httpfs, Evidence, postgres, образ minio elestio, Node-образы) — сверка с апстримом: есть ли патчи/правки кода/форки/vendored-изменения. **Настройка (env/YAML/конфиги/compose) — НЕ правка, в реестр не входит.** Собственный код (обёртки cube.js, MCP-сервер, harness, модели sqlmesh/cube) — не «правки компонентов», перечисляется отдельно как собственный слой | реестр «компонент → пин → кодовые отклонения (ожидаемо: 0)» зафиксирован в доках; воспроизводимость подтверждает, что любые компоненты заменяемы на апстрим-релизы без патчей | ✅ 2026-10-29 (`docs/upstream-components.md`: 13 компонентов → **0 отклонений**; проверки: git ls-files без .patch/.so/.wasm, npm ci без patchedDependencies/postinstall, uv.lock без tool.uv.patch/path-депов, Dockerfile'ы без правки апстрима; overrides Evidence — дословно апстрим-шаблон legacy (сверено с github evidence-dev/template), update-evidence-packages.js — файл шаблона; расширения — INSTALL из офиц. репо (REPOSITORY), пин = движок 1.5.5; elestio/minio = офиц. бинарник RELEASE.2025-09-07 + mc по digest; собственный слой перечислен отдельно) |
| 10 | **Тестирование пользователем (UAT)**: сценарный прогон по user-guide — быстрый старт с нуля (compose), file-демо (verify/bench, Evidence), ducklake-тренировка (seed-lake→apply-lake→verify-lake), смена sf (rebuild), RBAC-демо (прод-контейнер), MCP-агент (сценарии docs/cube-mcp.md) | все сценарии пройдены пользователем; замечания закрыты или заведены как fast-follow (реестр §9) | ✅ 2026-10-29 (прогон по §12 user-guide; найденное закрыто в доках на ходу: прод/dev — dev по умолчанию, Playground доступен (71b865f); остановка стека по режимам (a593928); вопрос PoP января — проконсультирован через MCP-куб sales_mov (−0.72% к дек.1996, +0.55% к янв.1996), rel_pop/rel_yoy — размерности, не меры; fast-follow в бэклог: №15 факт PLAN другой гранулярности) |

**Смена sf (процедура, оба режима):**
- Инвариант: `seed(sf)` меняет только raw-данные; sqlmesh строит витрину по **state** (хэши
  моделей, не данные) — без сброса state план пуст, marts остаются старыми. Смена sf =
  reseed + сброс state + полный ребилд + **перематериализация Evidence sources** (кэш
  материализован со старым sf) + `just verify`/bench (сравнение только внутри sf).
- file-режим: `stack.sh rebuild SF` — down (lock) → rename-бэкап (data+state в одном
  файле — сбрасываются вместе) → seed → apply → up → sources; сбой → авто-восстановление.
- ducklake-режим (шаги 3–8): куб НЕ останавливаем (снапшот-изоляция каталога, zero-downtime
  swap); dbgen во временный локальный файл → CTAS в `lake.raw_tpch` одной транзакцией;
  state sqlmesh — локальный .duckdb, сбрасывается **отдельным явным шагом** (развязано
  с данными); сбой на середине откатывается транзакцией каталога (старый снапшот жив);
  старый sf остаётся в time-travel снапшотах (анализ sf=1↔sf=10) → повторные смены растят
  MinIO, prune — флагом rebuild (`--prune-old`, шаг 8).
- Маркер sf: rebuild записывает текущий sf (артефакт + мета в каталоге); тесты counts
  читают его: целые sf → линейные ожидания (region=5/nation=25 — константы), дробные →
  skip. Устраняет текущие 11 красных тестов при sf=10.

Параллельно (из исходного плана): рост sf (10, …) + повторный прогон harness.

## 6. Риски

| Риск | Митигция |
|---|---|
| Официальный Cube MCP-пакет не найден в npm (404 на `@cubejs-backend/mcp`) | **Реализовался** (Stage 3): fallback REST/SQL API принят; harness от MCP не зависит |
| Смешение версий DuckDB (системный CLI 2.0 vs venv 1.5.5) | guard `cli-readonly`, всё воспроизводимо скриптами |
| Версии каталога ducklake расходятся между движками (0.3 у 1.4.4 vs 1.0 у 1.5.x) | **Реализовался** (2026-10-28, матрица): единый пин 1.5.5 + тест-пин + READ_ONLY attach (Stage 6 update, `docs/gotchas.md`) |
| S3-hop искажает сравнение latency (файл vs ducklake) | два режима в bench-protocol (шаг 9), цифры не смешиваются |
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
| 15 | 2026-10-27 | RBAC в Cube OSS до Ducklake (Stage 7): `access_policy` (member_level + row_level) на view `sales`/кубы + `contextToGroups` из JWT-claims + per-role `checkSqlAuth` SQL API; демо «admin всё / user 3 меры и свой регион» на REST+SQL API+MCP; стек переведён в прод-режим (dev mode отключает авторизацию; `pgSqlPort`, `cacheAndQueueDriver: 'memory'`); токены `scripts/make-cube-token.py`, admin-JWT автоминтом в harness/MCP; TDD-матрица `test_rbac.py` 19 тестов (verify 88/88) | RBAC (docs/cube-rbac.md) |
| 16 | 2026-10-28 | Матрица совместимости ducklake: каталог v0.3 (python 1.4.4) vs v1.0 (node 1.5.5) — несовместимы в обе стороны на любом типе каталога; AUTOMATIC_MIGRATION одностороняя/разрушающая → бамп `duckdb==1.5.5` в обоих python-пакетах (выравнено с `@duckdb/node-api` 1.5.5 движка Cube); фикс сборки pocketstack-sqlmesh (hatchling: setuptools flat-layout падал на `logs/`); verify 88/88 на выравненном стеке | Stage 6 update / Stage 7, `docs/gotchas.md` |
| 17 | 2026-10-28 | Старт Stage 7: `docker-compose.yml` — каталог postgres:17 + MinIO + mc-init бакета (healthchecks, порты только 127.0.0.1, секреты из .env с `:?`-гардами); зафиксированы решения и дорожная карта 9 шагов | Stage 7 |
| 18 | 2026-10-29 | Шаг 9 п.3 (решение пользователя): `scripts/stack.sh` УДАЛЁН целиком (5/6 команд мертвы после контейнеризации, rebuild дублирован Justfile); транзакционный бэкап (rename→build→rollback) перенесён в `just rebuild`; compose-фикс: minio-init уведён в профиль `init` — one-shot exited(0) ломал `up -d --wait` (exit 1) → `just lake-init` (`compose run --rm minio-init`), встроен в seed-lake/rebuild-lake; приёмка: up --wait=0, serve-up=0, rebuild 10 (бэкап→успех→удалён), sources, verify 88/1 | Stage 9 |
| 19 | 2026-10-29 | Шаг 9.1: аудит кодовых отклонений — реестр `docs/upstream-components.md`: 13 сторонних компонентов (движки, расширения, Cube/sqlmesh/Evidence, образы) → **0 патчей/форков/vendored**; npm-`overrides` Evidence сверены с апстрим-шаблоном (дословно); собственный слой (cube.js-обёртка, MCP, harness, модели, docker/скрипты) перечислен отдельно; воспроизводимые проверки в реестре | Stage 9.1 |
| 20 | 2026-10-29 | Шаг 9 п.2: актуализация доков — README: два режима DWH (DuckDB file / DuckLake) + быстрые старты обоих; user-guide переписан: с нуля file (§3) и ducklake (§4) отдельно, переход между режимами (§5), смена sf (§6), §12 чек-лист UAT (7 сценариев = шаг 10 плана); cube-rbac (режимы сервера — контейнер-первичны), cube-mcp, cube-sql-clients — serve-up вместо host-стека; evidence-setup → host-runbook (контейнер основной); исключения (не переписывались): gotchas, plan, bench-protocol, исследовательские снимки oss-vs-ent/bi-tools | Stage 9 |
| 21 | 2026-10-29 | Шаг 10 UAT закрыт пользователем по §12 user-guide. Находки закрыты на ходу: dev-режим куба по умолчанию во всех сценариях (Playground доступен; прод — явной опцией для RBAC, 71b865f); остановка стека по режимам — таблица в §7 + README (a593928); консультация PoP января через MCP (продемонстрирован сценарий агента). Fast-follow в бэклог: №15 факт PLAN. **Stage 7 закрыта целиком (шаги 1–10)** | Stage 7 закрыта |

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
| 10 | Контейнеризация: какие компоненты переносим в docker compose | ✅ решён | 2026-10-28 | **Вариант A**: только serving (cube+evidence) в контейнерах; pipeline (seed/sqlmesh), harness, MCP (stdio) — на хосте; bind-mount `./warehouse` сохраняет совместимость с хостовыми инструментами; порты публикуются на 127.0.0.1 (закрывает 0.0.0.0-дыру Cube dev) |
| 11 | DuckLake: один режим хранения или два | ✅ решён | 2026-10-28 | Два: файловый — основной (демо), ducklake — опция для тренировок; переключатель `WAREHOUSE_MODE=file\|ducklake` |
| 12 | Time-travel снапшоты ducklake: хранить или гасить | ✅ решён | 2026-10-28 | Храним (анализ через `ducklake_snapshots()`) + механизм чистки: снапшот-expiry и `mc rm` сирот (Stage 7, шаг 8) |
| 13 | Evidence в ducklake-режиме: через Cube SQL API или напрямую к lake | ✅ решён | 2026-10-28 | Только через Cube SQL API (pg-wire); прямой `type: duckdb`-коннектор к lake не подключаем |
| 14 | Тип каталога и объектного хранилища ducklake | ✅ решён | 2026-10-28 | PostgreSQL 17 (каталог) + MinIO (S3, parquet); поднимается `docker compose up -d --wait` |
| 16 | **Бэклог-1 (первый по порядку, решение пользователя 2026-10-29): «родной» бенчмарк TPC-H для DuckDB и DuckLake** — 22 запроса TPC-H из расширения tpch (`tpch_queries()`) против dbgen-схемы, без нашего семантического слоя: чистый базлайн движка. Для DuckLake «родного» бенчмарка нет — сделать тот же прогон поверх lake-каталога (парquet через S3). Результат — ОДНА таблица сравнения по каждому запросу (Q1–Q22: file vs ducklake, мс) + итог (Σ/медиана); зафиксировать в `results/` + док (расширение bench-protocol или отдельный doc). Бонус: валидация ответов `tpch_answers()` | 🔄 открыт (первый в бэклоге; старт следующей сессии) | 2026-10-29 | кандидат реализации: скрипт/just-recipe `tpch-bench` (file) / `tpch-bench-lake`; ВАЖНО: seed_tpch DROP'ает main-таблицы dbgen после копии в raw_tpch → для «родного» прогона нужен отдельный dbgen-запуск (tmp-файл как в seed_ducklake) или рерайт таблиц в lake.raw_tpch; тайминги — повторы N=3, p50, как bench-protocol |
| 15 | **Бэклог-2: вторая таблица фактов другой гранулярности** (например, данные плана/budget: гранулярность месяц × регион × сегмент против постатейной fact_sales) на **общих (conformed) измерениях** `dim_customer`/`dim_date` — оценить работу Cube: разрезы через shared dims из двух фактов, отношение план/факт (деление мер разных гранулярностей), влияние на pre-aggregation/кэш и на паритет harness (новые golden-вопросы план vs факт) | 🔄 открыт (бэклог, после №16) | 2026-10-29 | кандидат: `marts.fact_plan` (sqlmesh-модель) + куб/меры Cube (`plan_revenue`, `plan_vs_fact_ratio`); генерация плана — детерминированный скрипт поверх тех же raw (своего dbgen нет) |
