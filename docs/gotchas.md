# Нюансы и грабли pocketstack (living doc)

Живой документ: всё, что найдено в бою. Обновлять при каждом новом нюансе.
Формат: **симптом → причина → решение**.

---

## DuckDB: версии и блокировки

### Системный CLI 2.0 vs venv 1.5.5
- **Симптом**: файл warehouse становится нечитаем для Cube/sqlmesh/node-duckdb.
- **Причина**: запись/чекпойнт системным DuckDB 2.0 поднимает версию формата файла.
  Эмпирически (Stage 6 watch, 2026-10-26): 2.0 пишет формат v999; движок 1.5.5 читает
  только v64–68 → «Trying to read a database file with version number 999…».
- **Решение**: системный CLI — только `just cli-readonly`. Всё записное — через venv 1.5.5.
  Следствие: миграция на 2.0 возможна только всем стеком разом (npm-биндинги Cube/Evidence
  + sqlmesh), см. `docs/plan.md` Stage 6.

### ducklake: один каталог = один DATA_PATH
- **Симптом**: `DATA_PATH parameter "s3://bucket/warehouse/" does not match existing data path
  in the catalog "s3://bucket/probe/"` при ATTACH.
- **Причина**: pg-каталог запоминает data-path первой ATTACH-ии и сверяет его при каждом
  подключении; сменить префикс на живом каталоге нельзя (`OVERRIDE_DATA_PATH` — только
  осознанно, файлы расползутся по префиксам).
- **Решение**: канонический `DATA_PATH = s3://<bucket>/` (корень); структуру задаём
  схемами ducklake (`raw_tpch/`, `marts/` — dir-per-table), а не префиксами ATTACH.

### ducklake: PRIMARY KEY / UNIQUE не поддерживаются
- **Симптом**: `Not implemented Error: PRIMARY KEY/UNIQUE constraints are not supported
  in DuckLake` на CREATE TABLE.
- **Решение**: таблицы без констрейнтов; уникальность ключей мелких мета-таблиц —
  паттерном DELETE+INSERT (`pocketstack_meta` в seed_tpch.py).

### dbgen: lineitem нелинеен от sf
- **Симптом**: при sf=10 lineitem = 59 986 052, а не 6 001 215×10 = 60 012 150
  (orders при этом ровно 15 000 000).
- **Причина**: dbgen порождает 1–7 строк lineitem на заказ с рандомизацией; счётчик
  детерминирован для каждого sf, но не кратен sf=1.
- **Решение**: в тестах допуск 0.1% для lineitem/fact_sales
  (`tests/conftest.py: APPROX_REL`), остальные таблицы и dim_* линейны точно,
  region/nation — константы (5/25).

### Cube + ducklake: алиас каталога = «pocketstack», init на каждом коннекте
- **Симптом**: `Binder Error: Catalog "pocketstack" does not exist!` — семантическая
  модель адресует хранилище трёхчастно (`pocketstack.marts.*`, имя = стем файла в
  file-режиме), а ducklake-каталог зааттачен под другим алиасом.
- **Причина**: initSql/ATTACH — свойства сессии; пул коннектов Cube инициализирует
  каждый коннект отдельно (хук `configureConnection`), алиас каталога из модели —
  договорённость, не физическое имя.
- **Решение**: ducklake-каталог аттачится `AS pocketstack` — модель не меняется,
  логическое имя хранилища одинаково в file/ducklake; вся инициализация
  (расширения → SET s3_* → ATTACH READ_ONLY → USE) — в override
  `TimingDuckDBDriver.configureConnection` (cube.js). READ_ONLY — защита от случайной
  AUTOMATIC_MIGRATION каталога читателем. Стресс-сравнение ответов пула — только по
  `data` (lastUpdatedTime/requestId легитимно уникальны), `scripts/cube_stress.py`.

### sqlmesh + ducklake: lake — каталог по умолчанию (не search_path)
- **Симптом**: `Catalog Error: Schema with name sqlmesh__marts does not exist!`,
  попытки писать в `"memory"."marts".*`.
- **Причина**: sqlmesh квалифицирует имена каталогом по умолчанию; при
  `database: ":memory:"` + ATTACH lake весь физический слой уезжает в память,
  search_path не спасает (квалификация явная). Плюс sqlmesh запрещает
  `database` вместе с `catalogs` («первый entry = каталог по умолчанию»).
- **Решение**: в gateway `lake` каталог ducklake — ПЕРВЫЙ (и единственный) entry
  `catalogs`; физика тогда `lake.sqlmesh__marts.*`, прод-view `lake.marts.*`,
  `raw_tpch.*` резолвится сюда же. Секреты — Jinja `{{ env_var('X') }}` в config.yaml.


- **Симптом**: `DuckLake catalog version mismatch: catalog version is 0.3, but the
  extension requires version 1.0` при attach каталога, созданного другим движком.
- **Причина**: версия каталога привязана к сборке ducklake-расширения конкретного движка:
  python 1.4.4 → v0.3, node 1.5.5 → v1.0. Не зависит от типа каталога (файл/postgres).
  `AUTOMATIC_MIGRATION TRUE` односторонняя: после неё старый клиент каталог не открывает
  (плюс storage-версия файла каталога становится v68 > v67).
- **Решение**: все движки на одной версии DuckDB (пины 1.5.5, выравнено 2026-10-28);
  каталог создаёт эта же версия; Cube в ducklake-схеме аттачится READ_ONLY.

### Cube держит блокировку warehouse
- **Симптом**: `sqlmesh plan` падает `Could not set lock on file ... Conflicting lock is held in node`.
- **Причина**: node-процесс cubejs-server держит файл даже при `ATTACH ... (READ_ONLY)`.
- **Решение**: остановить cube перед apply, поднять после. Писать в READ_ONLY-режиме всё равно нельзя (нужен exclusive lock писателя).

### Убийство фоновых процессов
- **Симптом**: `pkill -f cubejs-server` роняет shell-инструмент (`ChildProcess.kill`), сервер умирает, но связка команд не догоняет.
- **Решение**: убивать по точному PID (`kill <pid>`), стартовать длиноживущие серверы через
  `setsid nohup env X=Y cmd > log 2>&1 < /dev/null & disown` — иначе таймаут шелла убивает группу процессов.

---

## Cube (1.8.13)

### Dev mode: авторизация отключена, но access_policy ПРИМЕНЯЕТСЯ
- **Симптом**: в dev-режиме запрос из Playground (без Authorization) возвращал
  пустой результат: access_policy не нашла групп → deny by default (`WHERE 1=0`,
  сегмент `rlsAccessDenied` в echo запроса). Ранняя версия этого гоча
  («любой запрос = admin, политики не применяются») была неверной.
- **Причина**: dev отключает только проверку токенов (403 не будет), но
  `access_policy` компилируется в SQL всегда; Playground ходит без токена →
  `securityContext` пуст → групп нет.
- **Решение**: dev-фолбэк в `contextToGroups` (`cube.js`): при
  `CUBEJS_DEV_MODE=true` запрос без групп получает `['admin']`. Итог: Playground
  (без токена) = admin; запрос с user-токеном в dev режется как в проде
  (регион + member_level, см. `tests/test_dev_mode.py`). Полный RBAC-прогон —
  прод: `just cube-prod`; в dev RBAC-тесты скипаются (guard в `test_rbac.py`).
  Сырой `CUBEJS_API_SECRET` как токен в проде даёт 403 (только подписанные JWT)
  — harness/MCP минтят admin-JWT сами (`harness/tokens.py`).

### Прод-режим: pgSqlPort и Cube Store не подразумеваются
- **Симптом**: SQL API :15432 не поднимается; `/v1/load` падает «Cube Store was specified as queue/cache driver».
- **Причина**: дефолты `pgSqlPort=15432` и in-memory очереди — только dev-mode фичи; в проде `NODE_ENV=production` требует Cube Store.
- **Решение**: в `cube.js` заданы `pgSqlPort: 15432` и `cacheAndQueueDriver: 'memory'`.

### access_policy: подлежащий куб под view участвует в RLS
- **Симптом**: admin-only политика на `fact_sales` + user-политика на view `sales` → любые запросы витрины под user компилируются в `WHERE 1=0` (молча!).
- **Причина**: RLS-проход идёт по всем кубам запроса, включая факт под витриной; не совпало ни с одной политикой факта → deny.
- **Решение**: политике `group: "*"` с `member_level: { includes: [] }` на факт-кубе: прямые запросы — deny, через view члены выдаются автоматически (view = security boundary). Плюс: пути членов (`dim_customer.customer_region`) в политиках куба запрещены — межкубовые row-фильтры пишите на view.

### Члены view — плоские, алиас не префиксует
- **Симптом**: `UserError: 'calendar' not found for path 'sales.calendar'`.
- **Причина**: в Views YAML `alias` неймспейсует только join_path; имена членов остаются `sales.year`.
- **Решение**: в запросах — `sales.year`, `sales.quarter`... Префикс появится только при коллизии имён.

### initSql — только строка, не массив
- **Симптом**: `Catalog "pocketstack" does not exist!` — ATTACH «не выполнился».
- **Причина**: драйвер duckdb принимает initSql строкой; массив не интерпретируется как список стейтментов.
- **Решение**: `[...].join('; ')` — одна строка через `;`.

### Кэш /v1/load отдаёт data без type=".query"
- **Симптом**: поллинг-клиент ждёт `type: ".query"`, кэшированный ответ его не содержит.
- **Решение**: критерий готовности — наличие ключа `data` в payload.

### SQL API (pg-wire): агрегат обязан соответствовать типу меры
- **Симптом**: `Measure aggregation type doesn't match ... COUNTDISTINCT() but SUM() was provided`.
- **Правила**: sum → `SUM(m)`, avg → `AVG(m)` (переписывается корректно, не avg-of-avg), count → `COUNT(m)`, count_distinct → `COUNT(DISTINCT m)`.
- Мера без агрегата в SELECT не резолвится (`could not be resolved from available columns`).
- **Уточнение (2026-10-26, проверено)**: числовые меры допускают и чужие агрегаты
  (`AVG(sales_mov.revenue)` → средняя месячная выручка, корректно); mismatch-ошибка
  воспроизводится на спец-мерах (count_distinct и т.п.). Агрегат по **измерению** тоже
  работает: `SUM(sales_mov.abs_yoy)` за 1997 = −103,374,792.92 = rollup меры
  `abs_yoy_sum` (независимая сверка KPI). Интроспекцию pg-клиенты получают через
  information_schema (кубы = `public.*`) — DBeaver/DBX подключаются штатно
  (см. `docs/cube-sql-clients.md`).

### Кэш ломает ground-truth проверки
- **Симптом**: повторный `/v1/load` не порождает запрос к БД → в логе его нет.
- **Решение**: body `{"query": {...}, "renewQuery": true}`.

### Evidence не интерполирует ${VAR} в connection.yaml (40.1.8)
- **Симптом**: `password authentication failed for user "${CUBESQL_USER}"` —
  литеральная строка ушла как логин.
- **Решение**: рендер из шаблона — `connection.yaml.example` (плейсхолдеры
  `__CUBESQL_USER__`/`__CUBESQL_PASSWORD__`) скриптом
  `scripts/render-evidence-connection.sh` (source-ит .env). Реальный
  connection.yaml — вне git (.gitignore), .env — вне git.

### Секреты: только .env, без фолбэков в коде (2026-10-26)
- Креды Cube (apiSecret, SQL API user/password) живут в `.env` (шаблон
  `.env.example`, пароли через `openssl rand -hex 32`, chmod 600).
- cube.js / harness (conftest, bench) требуют переменные и падают с понятной
  ошибкой, если .env нет — дефолтных кредов в коде больше НЕТ (старые
  `sql-user`/`sql-password` из git-истории более не работают).
- Загрузка .env: cube.js (собственный парсер), harness `harness/env.py`
  (`load_env()`, `setdefault` — внешние переменные приоритетнее), Justfile
  (`set dotenv-load := true`), stack.sh (`set -a; . .env; set +a`).
- Ловушка имени: в cube.js был `CUBEJS_SQL_PASSWORD`, в harness `CUBESQL_PASSWORD`
  — «работало» только из-за совпадающих фолбэков. Единые имена: `CUBESQL_USER`,
  `CUBESQL_PASSWORD`.

### MCP SDK: 2.x переименовал FastMCP (2026-10-26)
- **Симптом**: `No module named 'mcp.server.fastmcp'. This is mcp 2.x, where
  FastMCP was renamed to MCPServer` — uv резолвит mcp 2.x по `mcp>=1`.
- **Решение**: пин `mcp>=1.2,<2` (packages/mcp/pyproject.toml).
- Tool-аннотации в v1: `from mcp.types import ToolAnnotations` (НЕ `Annotations` —
  тот для контента; pydantic-ошибка `Tool.annotations: expected ToolAnnotations`).
- E2e-тест stdio: `mcp.ClientSession` + `mcp.client.stdio.stdio_client`,
  `StdioServerParameters(command=sys.executable, args=["-m", "cube_mcp"], cwd=REPO)`.

### pocketstack-harness не устанавливался как пакет (2026-10-26)
- **Симптом**: `import harness` падал — setuptools flat-layout без build-system
  ставил только `stage2_smoke`; тесты работали через sys.path-хак conftest.
- **Решение**: build-system hatchling + `packages = ["harness"]` в
  packages/harness/pyproject.toml → editable-установка пакета `harness`.

### Лог запросов DuckDB: формат с таймингами (2026-10-26)
- Пишет НЕ движок (`SET log_query_path` — только голый SQL, без времени), а
  **обёртка драйвера** в `packages/cube/cube.js` (`TimingDuckDBDriver.query()`).
- Формат: `started_at,finished_at,duration_ms,status,sql` — одна строка на запрос,
  SQL схлопнут в одну строку, статус OK/ERR (ERR пишет и при исключении).
- Парсер harness (`test_ground_truth.py`) ищет нормализованный SQL как подстроку —
  префиксные поля времени не мешают; тест дополнительно проверяет, что строка
  распарсилась и `duration_ms ≥ 0` (старые записи голым SQL не проходят — их
  строки многострочные; в истории файла могут оставаться, тесту не мешают).
- Если вернуть `SET log_query_path` в initSql — будет двойная запись (движок +
  обёртка): не делайте так.

### Cube MCP не существует в npm
- `@cubejs-backend/mcp` → 404 (проверено 2026-10-25). Fallback по плану рисков: REST/SQL API; harness от MCP не зависит.

### Прочее
- Dev mode: аутентификация отключена, header Authorization игнорируется; Playground на `:4000`, SQL API на `:15432` (`dbname='default'`, креды — из `.env`, см. раздел security выше).
- Pre-aggregations OFF принципиально — иначе SQL-паритет теряет смысл.

---

## DuckDB: SQL и логи

### log_query_path пишет многострочные запросы
- **Симптом**: построчный CSV-парсинг режет один запрос на строки, substring-матч не работает.
- **Решение**: нормализовать (схлопнуть whitespace) весь текст файла и искать вхождение нормализованного SQL.
- В лог попадают и служебные запросы (SELECT 1, refresh_key) — это нормально, ищем конкретное вхождение.

### range() с датами
- `range(DATE, DATE, INTERVAL)` возвращает TIMESTAMP → `CAST(d AS DATE)`.
- Конец exclusive → верхняя граница `+ INTERVAL 1 DAY`.

### TPC-H: extendedprice уже содержит количество
- `l_extendedprice = l_quantity × p_retailprice` (проверено: 0 расхождений на 6M строк).
- Revenue = `SUM(l_extendedprice × (1 − l_discount))`. Умножать ещё раз на qty — двойной счёт.
- discount/tax — проценты на строку: арифметика до агрегации, не после.

### Decimal-округление
- Python `Decimal.quantize` по умолчанию — banker's rounding (100.005 → 100.00).
- Для сравнения денег между путями: явно `rounding=ROUND_HALF_UP`.

---

## sqlmesh

- `.cache/` в каталоге пакета — в `.gitignore` (мусор от plan/apply).
- CI-режим: `sqlmesh plan --auto-apply --no-prompts`.
- Warehouse полностью воспроизводим: `just reset` (dbgen + sqlmesh) — откат любой аварии дешёвый.

---

## Окружение

- **just не ставился системой**: `uv tool install rust-just` → `~/.local/bin/just` (проверять PATH).
- **Chrome для chrome-devtools MCP отсутствует** (`/opt/google/chrome/chrome`): доступен
  puppeteer-кеш `~/.cache/puppeteer/chrome/*/chrome-linux64/chrome` через `puppeteer-core` + Firefox для интерактива.
- **artifacts/ — в корне репо**, не в packages/*: `artifacts/verify-report.md` — в git,
  `artifacts/duckdb_query_log.csv` — gitignored.

---

## Эталоны для сверки

- TPC-H sf=1 rowcounts: region 5, nation 25, supplier 10 000, customer 150 000,
  part 200 000, partsupp 800 000, orders 1 500 000, lineitem 6 001 215.
- dim_date: union-диапазон `LEAST/GREATEST(ship_date, receipt_date)`, 1992-01-02..1998-12-31, 2557 дней.
- Выручка по годам (ship-календарь, млрд): 1992 ≈ 27.5, 1993 ≈ 33.0, 1994 ≈ 33.0,
  1995 ≈ 33.3, 1996 ≈ 33.2, 1997 ≈ 33.1, 1998 ≈ 24.9.

---

## Evidence 40.1.8 (Stage 4 — ✅ закрыта 2026-10-26)

### Архитектура данных (важно!)
- **Инлайн-запросы в страницах (` ```sql name `) исполняются в DuckDB-WASM** поверх
  материализованных parquet-таблиц, НЕ против живого источника.
- К живому Cube выполняются только `.sql`-файлы в `sources/cube/*.sql`
  (`npx evidence sources` — материализация). Схема в wasm: `cube.<имя_файла>`.
- Поэтому: вся метрика — файлами в `sources/cube/` (golden-SQL дословно!),
  страницы — тонкие обёртки `select * from cube.<id>` + фильтры `${inputs}` (wasm-side).

### Синтаксис и грабли
- ` ```sql name source=cube ` — НЕ ПОДДЕРЖАН в 40.1.8: весь заголовок fence идёт
  в `{#if ...}` → битый Svelte («Component was left open» и др.). Источник = каталог.
- YAML frontmatter: title с двоеточием обязательно в кавычки (`title: "Выручка: ..."`).
- Трюк: fence ` ```sql ` БЕЗ имени = просто подсвеченный CodeBlock (для показа SQL).
- Cube SQL API (pg-wire) через коннектор `type: postgres`: нативного `type: cube`
  в 40.1.8 НЕТ (исследование bi-tools-comparison оказалось оптимистичным).
- DuckDB-коннектор Evidence открывает файл READ-ONLY (безопасно с Cube одновременно);
  `filename` в connection.yaml — путь ОТ каталога источника (4 уровня вверх из
  sources/duckdb_local).

### Установка/версии
- `npm create evidence@latest` СЛОМАН (create-evidence без bin, 404) — шаблон брать:
  `git clone --depth 1 -b legacy https://github.com/evidence-dev/template`.
- Node 24 ломает SSR: `Cannot find module '__SERVER__/internal.js'` (sveltekit/vite).
  Рабочая связка — Node 20: бинарь в `~/.local/opt/node-v20.19.0-linux-x64/bin/node`,
  запуск: `PATH=~/.local/opt/node-v20.19.0-linux-x64/bin:$PATH npm run dev`.
- Ставить зависимости строго `npm ci --legacy-peer-deps` c package-lock из шаблона:
  самостоятельный `npm install` резолвит несовместимые версии.

### SQL API Cube: что НЕ умеет
- `AVG(дата − дата)` → interval не усредняется; `DATE_DIFF`/`EXTRACT` в обёртках
  переписывания не проходят. Решение: вычисляемое поле в модель (days_in_transit)
  или куб с SQL (sales_mov).
- Оконные функции и CTE — РАБОТАЮТ (проверено: SUM() OVER, WITH + self-join).

### Сдвиг месяца на границе года: `month - 1` даёт 0 вместо 12
- **Симптом**: PoP-отклонение января пустое (NULL) — «предыдущий месяц» не нашёлся.
- **Причина**: `JOIN m prev ON prev.month = cur.month - 1` — для января ищется month=0,
  а нужен декабрь ПРОШЛОГО года (month=12, year-1).
- **Решение**: непрерывный индекс `ym = year*12 + month`; сдвиги `prev.ym = cur.ym - 1`
  (месяц) и `ly.ym = cur.ym - 12` (год). Работает и в Cube SQL, и в DuckDB.
- **Урок harness**: паритет REST↔SQLAPI↔REF проходил 13/13, хотя баг был в самом кубе —
  эталон q13 содержал ТУ ЖЕ формулу (скопированную из куба). Эталон обязан строиться
  из НЕЗАВИСИМОЙ семантики; правка эталона первой (RED) вскрыла расхождение ровно
  в одной январской строке, куб догнан до эталона (GREEN, 69/69).

### Компоненты: подводные камни (проверено в браузере, 2026-10-26)
- `data=` в компонентах ТОЛЬКО в скобках: `data={query}`. Без скобок строка уходит
  в проп → `TypeError: data.map is not a function`, страница падает целиком.
- `summaryTotal/summarySum/summaryAvg` у BigValue **НЕ СУЩЕСТВУЮТ** в
  core-components 5.4.2 (молча игнорируются → показывается первая строка).
  Агрегаты: либо `<Value data agg=sum|avg|min|max|median>` (только SDK-Query),
  либо — по нашему правилу «метрики в Cube» — measures куба (sales_mov_kpi).
- `fmt=pct/pct1/pct2` умножают на 100 (ждут дробь). Если куб отдаёт процент-ПУНКТЫ
  (наш rel_yoy = 100·Δ/база) — pct даёт ×100 ошибку (0.55% → «55.5%»). Правильно:
  fmt=num2 + «%»/«п.п.» в заголовке.
- `sort=revenue-desc` невалиден и валит DataTable: только `sort=revenue desc`
  (в кавычках!) или `sort=revenue`.
- Golden-SQL без алиаса (`SELECT SUM(sales.revenue) FROM sales`) материализуется
  с колонкой буквально `"sum(sales.revenue)"` — ссылаться в запросе страницы только
  через двойные кавычки, лучше сразу алиасовать в v_*-обёртке.
- Легаси-шаблон недоустанавливает peer'ы: `@sveltejs/vite-plugin-svelte@^3`
  (под svelte 4.2/vite 5.4) и `autoprefixer` надо доставлять руками
  (`npm i -D ... --legacy-peer-deps`), иначе vite dev падает на старте.
- Ссылки между страницами — ТОЛЬКО абсолютные (`[X](/x)`): относительная `(verification)`
  с `/revenue` резолвится в `/revenue/verification` → 404 «page can't be found».
- Проверка страниц в headless: `scripts/visual-check.mjs` (puppeteer-core +
  системный Chrome из ~/.cache/puppeteer; ждёт 12с на DuckDB-WASM, ловит console
  errors, считает svg/canvas, снимает скриншоты). `__data.json` в dev = null —
  НОРМА (wasm исполняет запросы в браузере), реальная проверка только через DOM.
