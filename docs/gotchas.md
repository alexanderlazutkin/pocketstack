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
