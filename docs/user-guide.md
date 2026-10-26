# Руководство пользователя pocketstack

Пошаговая инструкция: установка, запуск, смена объёма данных (sf), разблокировка
DuckDB, сценарий сверки цифр через UI Cube и Evidence BI, где смотреть отчёты
тестов и производительности.

---

## 1. Предусловия

| Инструмент | Версия/путь | Проверка |
|---|---|---|
| Linux (bash) | — | — |
| [uv](https://docs.astral.sh/uv/) (Python 3.12) | актуальный | `uv --version` |
| Node.js | **20.x**, user-local `~/.local/opt/node-v20.19.0-linux-x64/` | `~/.local/opt/node-v20.19.0-linux-x64/bin/node --version` |
| just (опц.) | `uv tool install rust-just` → `~/.local/bin/just` | `just --version` |
| Chrome (опц.) | для автопроверки страниц Evidence | — |

Node 20 обязателен для Evidence (системный Node 24 ломает SSR — `docs/gotchas.md`).
Установка — user-local, без глобальных изменений:

```bash
mkdir -p ~/.local/opt && cd ~/.local/opt
curl -fsSLO https://nodejs.org/dist/v20.19.0/node-v20.19.0-linux-x64.tar.xz
tar xf node-v20.19.0-linux-x64.tar.xz && rm node-v20.19.0-linux-x64.tar.xz
```

## 2. Установка проекта с нуля

```bash
git clone <repo-url> pocketstack && cd pocketstack

# Секреты (вне git): скопируйте шаблон и сгенерируйте свои значения
cp .env.example .env
$EDITOR .env        # CUBEJS_API_SECRET и CUBESQL_PASSWORD: openssl rand -hex 32

# Python-окружение (sqlmesh, harness, duckdb 1.4.4)
uv sync

# Зависимости Evidence (строго ci + legacy-peer-deps, см. docs/evidence-setup.md)
cd packages/evidence && npm ci --legacy-peer-deps && cd ../..

# БД + витрины + стек + материализация — одной командой (sf=1 по умолчанию)
scripts/stack.sh rebuild
```

`rebuild` транзакционен: старая БД переименовывается в бэкап, создаётся новая,
при успехе бэкап удаляется, при сбое — авто-восстановление.
Занимает ~10–15 минут (dbgen + sqlmesh + материализация 22 таблиц).

Готово: **Evidence** http://localhost:3000 · **Cube UI** http://localhost:4000.

## 3. Смена объёма данных (sf)

```bash
scripts/stack.sh rebuild 2      # TPC-H sf=2 (данные и все цифры изменятся)
scripts/stack.sh rebuild 0.1    # крохотный сет для быстрых экспериментов
# эквивалент по шагам (стек должен быть остановлен!):
just seed 2 && just apply && scripts/stack.sh up && scripts/stack.sh sources
```

После смены sf прогоните проверки (§6): при ЛЮБОМ sf должно сходиться
равенство трёх путей; абсолютные числа масштабируются с данными.

## 4. Ежедневный запуск и остановка

```bash
scripts/stack.sh status    # Cube :4000, SQL API :15432, Evidence :3000, размер БД
scripts/stack.sh up        # поднять (идемпотентно: работающее не трогает)
scripts/stack.sh down      # остановить всё
scripts/stack.sh sources   # перематериализовать Evidence из Cube (после just apply)
```

Логи серверов: `artifacts/logs/cube.log`, `artifacts/logs/evidence.log`.

## 5. Разблокировка DuckDB

**Симптом**: `just apply` / `just seed` / `sqlmesh plan` падает с
`Conflicting lock`, `Could not set lock on file ... pocketstack.duckdb` или
`IO Error: trying to read a database file that is already open`.

**Причина**: файл на запись открывает ровно один процесс. Писатель — sqlmesh;
Cube/Evidence держат файл и не дают применить изменения витрины.

**Лечение** (две команды):

```bash
scripts/stack.sh down      # остановить держателей блокировки (+ фолбэк-pkill)
just apply                 # повторить запись

# затем вернуть стек:
scripts/stack.sh up
scripts/stack.sh sources   # если менялись данные (дашборды увидят новые цифры)
```

`scripts/stack.sh rebuild [sf]` делает это сам (down в начале).
Если :4000/:3000 после `down` всё ещё заняты — найдите процесс вручную:
`lsof -i :4000 -i :3000`, `kill <pid>`.

Отдельно: системный DuckDB CLI 2.0 к файлам проекта — ТОЛЬКО `just cli-readonly`
(запись версией 2.0 сделает файл нечитаемым для 1.4.x — весь стек на ней).

## 6. Сценарий сверки цифр (Cube UI + Evidence BI)

Смысл: одна и та же метрика, полученная тремя путями, должна совпасть до копейки.
Разберите с пользователем на примере **total_revenue** (sf=1: 218,102,223,885.00).

**Шаг 1 — Cube UI (REST)**: http://localhost:4000 → вкладка **Explore/Playground**:
- Members → Measure: `Sales.revenue` → Run. Итог = Σ выручки.
- Добавьте Dimension `Sales.customer_region` — получите разрез, он же на дашборде.

**Шаг 2 — Cube SQL API (pg-wire)**: любой SQL-клиент (DBeaver/DBX, подключение —
`docs/cube-sql-clients.md`, `localhost:15432`, креды из вашего `.env`):

```sql
SELECT SUM(sales.revenue) FROM sales;
-- 1997 с отклонениями (куб sales_mov):
SELECT sales_mov.month, sales_mov.revenue, sales_mov.rel_yoy, sales_mov.rel_pop
FROM sales_mov WHERE sales_mov.year = 1997
GROUP BY 1,2,3,4 ORDER BY 1;
```

**Шаг 3 — Evidence BI**: http://localhost:3000 → страница **«Верификация: 13
golden-вопросов»**: блок `total_revenue` — BigValue «Σ выручка (REST = SQL API = REF)»
должен равняться шагам 1–2. Страница **«Выручка»** → KPI «Выручка, всего» — то же число.
Рядом с каждым блоком: «Проверяет» / «Используется» — где эта цифра живёт на дашбордах.

**Шаг 4 — автосверка harness** (то же самое, но всеми 13 вопросами сразу):

```bash
just verify    # 69 тестов
```

Если шаги 1–3 вручную равны, а `just verify` зелёный — стек честен по построению.

### Как harness доказывает цифры: три уровня

Каждый из 13 golden-вопросов проверяется тремя независимыми тестами:

| Уровень | Что доказывает | Как |
|---|---|---|
| **Паритет** (rows) | REST `/v1/load` ↔ SQL API (pg-wire) ↔ эталонный SQL к `marts.*` дают **одинаковые числа** | три пути выполняются, множества строк сравниваются |
| **Детерминизм** (SQL-hash) | Cube собирает SQL детерминированно (без «плавающих» планов) | SQL из `/v1/sql` хэшируется N раз, хэши равны |
| **Ground truth** (лог DuckDB) | число пути REST получено **реальным исполнением SQL над витриной**, а не из кэша Cube | см. ниже |

Механика ground truth: Cube стартует с логом запросов (`CUBEJS_DUCKDB_QUERY_LOG`,
обёртка драйвера в `packages/cube/cube.js`). Каждый исполненный запрос пишется
в `artifacts/duckdb_query_log.csv` одной строкой:

```
started_at,finished_at,duration_ms,status,sql
2026-10-26T11:41:11.157Z,2026-10-26T11:41:11.167Z,10,OK,SELECT "dim_date".year "sales__year", sum(...)
```

Тест берёт у самого Cube SQL, который он собирает для вопроса (`/v1/sql`),
выполняет вопрос через `/v1/load` с `renewQuery: true` (обход кэша — иначе Cube
ответит из кэша и в логе запроса не будет) и **ищет этот SQL в логе**: нашёлся →
запрос реально дошёл до DuckDB. Это защита от «красивого числа из кэша».

## 7. Где смотреть отчёты и логи

| Что | Где | Когда обновляется |
|---|---|---|
| Отчёт верификации (13 вопросов, паритет, ground truth) | `artifacts/verify-report.md` | каждый `just verify` |
| Лог запросов DuckDB: `started_at,finished_at,duration_ms,status,sql` (ground truth + фактическая длительность каждого запроса Cube) | `artifacts/duckdb_query_log.csv` | пишется обёрткой драйвера при каждом запросе |
| **Производительность**: сводный индекс прогонов | `results/index.md` | каждый `just bench` |
| **Производительность**: конкретный прогон | `results/runs/<дата-время>/summary.md` (человекочитаемо), `summary.csv`, `detail.csv` (latency 3 путей × повторы) | — |
| SQL каждого bench-вопроса | `results/queries/<id>.sql` | — |
| Протокол, как читать метрики | `docs/bench-protocol.md` | — |
| Логи серверов стека | `artifacts/logs/{cube,evidence}.log` | `scripts/stack.sh up` |
| Тесты витрины (контракт/star-schema) | `just test` → pytest вывод | после изменения моделей |

Пример чтения bench: `results/runs/<ts>/summary.md`, колонки — вопрос, строк,
latency REST / SQL API / Evidence-source (мс, медиана и лучший), SQL-hash.

## 8. Если что-то сломалось

- Страница Evidence пустая / ошибка консоли → `scripts/stack.sh restart` затем
  `scripts/stack.sh sources`; глубже — `docs/evidence-setup.md` (приёмка §5).
- Любая странность с цифрами → `just verify`; если красное — смотреть
  `artifacts/verify-report.md` какой вопрос и какой путь разошёлся.
- Полная пересборка → `scripts/stack.sh rebuild` (данные и витрины детерминированы).
- Словарь известных грабель → `docs/gotchas.md` (симптом → причина → решение).
