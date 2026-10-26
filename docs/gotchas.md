# Нюансы и грабли pocketstack (living doc)

Живой документ: всё, что найдено в бою. Обновлять при каждом новом нюансе.
Формат: **симптом → причина → решение**.

---

## DuckDB: версии и блокировки

### Системный CLI 2.0 vs venv 1.4.4
- **Симптом**: файл warehouse становится нечитаем для Cube/sqlmesh/node-duckdb.
- **Причина**: запись/чекпойнт системным DuckDB 2.0 поднимает версию формата файла.
- **Решение**: системный CLI — только `just cli-readonly`. Всё записное — через venv 1.4.4.

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

### Cube MCP не существует в npm
- `@cubejs-backend/mcp` → 404 (проверено 2026-10-25). Fallback по плану рисков: REST/SQL API; harness от MCP не зависит.

### Прочее
- Dev mode: аутентификация отключена, header Authorization игнорируется; Playground на `:4000`, SQL API на `:15432` (`dbname='default'`, sql-user/sql-password).
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
