# Руководство пользователя pocketstack

Пошаговое руководство: работа с нуля в двух режимах витрины (DuckDB-файл и
DuckLake-lakehouse), переход между режимами, смена объёма данных (sf), сверка
цифр, где смотреть отчёты и что делать при сбоях.

---

## 1. Два режима работы витрины

Витрина (marts) развёртывается в одном из двух режимов. Режим — свойство
**куба-контейнера** (переменная `WAREHOUSE_MODE` при его создании); модели
sqlmesh и семантика Cube одинаковы в обоих.

| | **DuckDB file** (основной) | **DuckLake** (lakehouse, опция) |
|---|---|---|
| Данные | один файл `warehouse/pocketstack.duckdb` | каталог в PostgreSQL + parquet в MinIO (docker compose) |
| Сильная сторона | простота, максимум скорости | time-travel, данные вне файла, zero-downtime смена sf |
| Построение | `just rebuild SF` | `just seed-lake SF` + `just apply-lake` |
| Проверка | `just verify` / `just bench` | `just verify-lake` / `just bench-lake` |
| Смена sf | `just rebuild SF` (куб останавливается) | `just rebuild-lake SF` (куб НЕ останавливается) |

Данные режимов **независимы** (у каждого свой raw и витрины; state sqlmesh у
lake — отдельный файл `warehouse/lake_state.duckdb`). Переход между режимами
не конвертирует данные — см. §5.

## 2. Предусловия

| Инструмент | Версия/путь | Проверка |
|---|---|---|
| Linux (bash) | — | — |
| [uv](https://docs.astral.sh/uv/) (Python 3.12) | актуальный | `uv --version` |
| Docker (Engine + compose v2 / Desktop) | актуальный | `docker compose version` |
| just (опц., но все команды ниже — через него) | `uv tool install rust-just` → `~/.local/bin/just` | `just --version` |

Serving-слой (Cube, Evidence) и lake-инфраструктура — в контейнерах; **Node на
хосте не нужен** (пины зашиты в образы `docker/`). На хосте работают только
pipeline (uv: sqlmesh/seed), harness и MCP-сервер.

## 3. С нуля: режим DuckDB (файл)

```bash
git clone <repo-url> pocketstack && cd pocketstack

# Секреты (вне git): шаблон + свои значения
cp .env.example .env
$EDITOR .env     # CUBEJS_API_SECRET, CUBESQL_PASSWORD, CUBESQL_RBAC_PASSWORD,
                 # DUCKLAKE_*: openssl rand -hex 32 (см. комментарии в шаблоне)

uv sync          # python-окружение: sqlmesh, harness, duckdb 1.5.5

just rebuild     # ВСЁ одним шагом (sf=1): снять лок куба → dbgen → витрины →
                 # контейнеры serving → материализация Evidence sources
```

`just rebuild` транзакционен: текущая БД переименовывается в бэкап, при успехе
бэкап удаляется, при сбое — авто-откат предыдущей БД. Занимает ~10–15 минут
на sf=10 (dbgen + sqlmesh + материализация).

Проверка стека:

```bash
just serve-up    # куб в dev: Playground :4000 (по умолчанию)
just verify      # тесты живого стека: паритет 3 путей + ground truth
                 # (в dev — без RBAC-матрицы; полный 88/88 — куб в проде:
                 #  CUBEJS_DEV_MODE=false just serve-up, затем just verify)
just bench       # 13 вопросов, latency 3 путей → results/
```

Готово: **Evidence** http://localhost:3000 · **Cube UI** http://localhost:4000 ·
SQL-клиенты — `docs/cube-sql-clients.md`.

## 4. С нуля: режим DuckLake (lakehouse)

```bash
docker compose up -d --wait   # 1) инфраструктура: pg-каталог + MinIO (healthchecks)

just seed-lake 1              # 2) бакет (идемпотентно) + dbgen sf=1 → CTAS в lake.raw_tpch
just apply-lake               # 3) витрины sqlmesh в lake (state — warehouse/lake_state.duckdb)

WAREHOUSE_MODE=ducklake just serve-up   # 4) куб на lake (dev — Playground :4000)

just verify-lake              # 5) те же тесты, что verify (RBAC — в проде, см. врезку);
                               #    ground truth — ATTACH lake READ_ONLY
just bench-lake               # бенч lake-режима (цифры file/lake не смешиваются)
```

> **Прод vs dev**: по умолчанию куб в dev (Playground, безтокенный admin).
> Полные 88 тестов `verify-lake` (вкл. RBAC-матрицу) требуют прод:
> пересоздать куб `WAREHOUSE_MODE=ducklake CUBEJS_DEV_MODE=false just serve-up`;
> в dev RBAC-тесты пропустятся (остальное — полноценно).

Нюансы lake-режима:
- куб аттачит каталог **READ_ONLY** (защита от случайной миграции каталога);
  пишет только sqlmesh/seed через свои транзакции в pg-каталоге;
- после смены данных в lake (`rebuild-lake`) куб может отдавать старые числа
  из своего кэша до `renewQuery`/TTL — harness обходит сам (грабля в gotchas);
- повторные `just rebuild-lake` не раздуливают MinIO: финальный `--prune-old`
  гасит time-travel и удаляет ненужные файлы;
- нужно time-travel для анализа (sf=1↔sf=10)? — шаги вручную БЕЗ чистки:
  `just seed-lake SF` → `rm warehouse/lake_state.duckdb*` → `just apply-lake`.

## 5. Переход между режимами

Данные режимов независимы и не конвертируются: в новом режиме будет тот sf,
который вы в него засеяли (или засейте — см. §3/§4). Переход = пересоздание
куба-контейнера с другим `WAREHOUSE_MODE` (compose видит смену env и
пересоздаёт контейнер; Evidence не трогаем — он ходит в куб по тем же портам).

**file → ducklake** (в lake ещё нет данных):

```bash
docker compose up -d --wait            # инфраструктура lake (если не поднята)
just seed-lake 1 && just apply-lake    # данные + витрины в lake (sf — ваш)
WAREHOUSE_MODE=ducklake just serve-up  # куб на lake (dev; прод — см. §7)
docker compose exec evidence npm run sources   # перематериализовать кэш Evidence
just verify-lake                       # сверка в lake-режиме (RBAC — в проде, см. §7)
```

**ducklake → file** (данные file уже есть — строились §3; иначе сначала `just rebuild`):

```bash
CUBEJS_DEV_MODE=false just serve-up    # куб без WAREHOUSE_MODE → file (пересоздастся)
docker compose exec evidence npm run sources
just verify
```

Текущий режим куба: `docker compose exec cube printenv WAREHOUSE_MODE`
(выведет `file` или `ducklake`; переменную задаёт compose — `${WAREHOUSE_MODE:-file}`).

## 6. Смена объёма данных (sf)

```bash
just rebuild 2        # file-режим: sf=2 (данные и все цифры изменятся)
just rebuild-lake 10  # lake-режим: sf=10, куб НЕ останавливается (zero-downtime)
just seed 0.1         # только raw без витрин (file), для быстрых экспериментов
```

После смены sf прогоните проверки (§9): при любом sf должно сходиться
равенство трёх путей; абсолютные числа масштабируются с данными.

## 7. Ежедневный запуск и остановка

```bash
just serve-up        # поднять cube+evidence (+ lake-инфраструктуру compose)
just serve-down      # снять serving, НЕ трогая lake-инфраструктуру
just evidence        # поднять только Evidence (с кубом)
docker compose ps    # состояние контейнеров
docker compose logs cube evidence   # логи серверов (или -f для слежения)
```

Прод/dev куба — переменной при поднятии: `CUBEJS_DEV_MODE=false just serve-up`
(прод: строгие токены + RBAC; dev — playground на :4000 и безтокенный admin).

### Остановка стека (по режимам)

| Что остановить | Команда | Комментарий |
|---|---|---|
| Только serving (куб+evidence) | `just serve-down` | Освобождает лок `warehouse/*.duckdb` — можно `just apply`/`seed`. Infra-контейнеры (pg, minio) продолжат работать |
| **Стек DuckDB (file) полностью** | `just serve-down` + `docker compose stop postgres minio` | Файл-витрина в `warehouse/` — данные на месте; pg/minio поднимаются serve-up'ом даже в file-режиме, потому их и останавливаем |
| **Стек DuckLake полностью** | `docker compose --profile serve stop` | Остановит и serving, и инфраструктуру (pg-каталог + MinIO); данные остаются в volumes. Обратно — `just serve-up` |
| Снести контейнеры (данные lake сохранить) | `docker compose --profile serve down` | Контейнеры удалятся, volumes (`pgdata`, `miniodata`) останутся |
| Снести всё, состояние «с нуля» | `docker compose --profile serve down -v` и `rm warehouse/*.duckdb*` | Удаляет volumes lake (каталог+бакет) и файлы file-режима; `.env` остаётся → старт по §3/§4 |

## 8. Разблокировка DuckDB (Conflicting lock)

**Симптом**: `just apply` / `just seed` / `sqlmesh plan` падает с
`Conflicting lock` или `Could not set lock on file ... pocketstack.duckdb`.

**Причина**: файл на запись открывает ровно один процесс; в file-режиме файл
держит контейнер куба.

```bash
just cube-stop    # снять лок куба (docker compose stop cube)
just apply        # повторить запись

just serve-up     # затем вернуть куб
```

`just rebuild` делает это сам. В **lake-режиме** остановка не нужна: писатели
координируются транзакциями pg-каталога (куб держит только READ_ONLY-attach).

Отдельно: системный DuckDB CLI 2.0 к файлам проекта — только `just cli-readonly`
(запись версией 2.0 сделает файл нечитаемым для 1.5.5 — весь стек на ней).

## 9. Сценарий сверки цифр (Cube UI + Evidence BI)

Смысл: одна и та же метрика, полученная тремя путями, должна совпасть до копейки.
Разберите на примере **total_revenue** (sf=1: 218,102,223,885.00).

**Шаг 1 — Cube UI (REST)**: http://localhost:4000 → **Explore/Playground**:
- Members → Measure: `Sales.revenue` → Run. Итог = Σ выручки.
- Добавьте Dimension `Sales.customer_region` — получите разрез, он же на дашборде.

**Шаг 2 — Cube SQL API (pg-wire)**: любой SQL-клиент (DBeaver/DBX —
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

**Шаг 4 — автосверка harness** (то же всеми 13 вопросами сразу):

```bash
just verify        # 88 тестов (в lake-режиме — just verify-lake)
```

Если шаги 1–3 вручную равны, а verify зелёный — стек честен по построению.

### Как harness доказывает цифры: три уровня

| Уровень | Что доказывает | Как |
|---|---|---|
| **Паритет** (rows) | REST `/v1/load` ↔ SQL API (pg-wire) ↔ эталонный SQL к `marts.*` дают **одинаковые числа** | три пути выполняются, множества строк сравниваются |
| **Детерминизм** (SQL-hash) | Cube собирает SQL детерминированно (без «плавающих» планов) | SQL из `/v1/sql` хэшируется N раз, хэши равны |
| **Ground truth** (лог DuckDB) | число пути REST получено **реальным исполнением SQL над витриной**, а не из кэша Cube | см. ниже |

Механика ground truth: куб-контейнер стартует с логом запросов
(`CUBEJS_DUCKDB_QUERY_LOG` → `artifacts/duckdb_query_log.csv`, bind-mount).
Тест берёт у Cube SQL для вопроса (`/v1/sql`), выполняет вопрос через `/v1/load`
с `renewQuery: true` (обход кэша) и **ищет этот SQL в логе**: нашёлся → запрос
реально дошёл до DuckDB. Это защита от «красивого числа из кэша».

## 10. Где смотреть отчёты и логи

| Что | Где | Когда обновляется |
|---|---|---|
| Отчёт верификации (13 вопросов, паритет, ground truth) | `artifacts/verify-report.md` | каждый `just verify` / `verify-lake` |
| Лог запросов DuckDB `started_at,finished_at,duration_ms,status,sql` (ground truth) | `artifacts/duckdb_query_log.csv` | каждым запросом куба |
| **Производительность**: индекс прогонов | `results/index.md` | каждый `just bench` / `bench-lake` |
| Конкретный прогон | `results/runs/<ts>/summary.md` (+ `.csv`) | — |
| SQL каждого bench-вопроса | `results/queries/<id>.sql` | — |
| Протокол метрик (два режима) | `docs/bench-protocol.md` | — |
| Логи серверов | `docker compose logs cube evidence` | — |
| Тесты витрины (контракт/star-schema) | `just test` | после изменения моделей |

## 11. Если что-то сломалось

- Страница Evidence пустая / ошибка консоли → `docker compose restart evidence`,
  затем `docker compose exec evidence npm run sources`; глубже —
  `docs/evidence-setup.md` (host-runbook для отладки).
- Любая странность с цифрами → `just verify` (`verify-lake`); красное — смотреть
  `artifacts/verify-report.md`: какой вопрос и какой путь разошёлся.
- Полная пересборка → `just rebuild [SF]` (file) / `just rebuild-lake [SF]` (lake)
  — данные детерминированы (dbgen + sqlmesh).
- Словарь известных грабель → `docs/gotchas.md` (симптом → причина → решение).
- AI-агенту (opencode/Claude Code) нужен доступ к метрикам → MCP-сервер
  `docs/cube-mcp.md` (подключается одной командой, read-only).

## 12. Чек-лист приёмки (UAT)

Прогон «как новый пользователь» — каждый сценарий ведёт разделами этого
руководства и соседних доков. Критерий закрытия: все строки пройдены,
замечания — в `docs/plan.md` §9 (реестр вопросов) как fast-follow.

| # | Сценарий | Где | Критерий успеха |
|---|---|---|---|
| 1 | Быстрый старт с нуля, file-режим | §3: clone → `.env` → `uv sync` → `just rebuild` | Evidence :3000 и Cube :4000 отвечают; `verify` **88/1** (куб в проде) |
| 2 | File-демо: сверка цифр + bench | §9 (три пути `total_revenue`) + `just bench` | число совпало на всех путях; bench 13/13 parity → `results/` |
| 3 | DuckLake с нуля | §4: `compose up` → `seed-lake` → `apply-lake` → `serve-up` (WAREHOUSE_MODE=ducklake) | `verify-lake` **88/1** (куб в проде: `WAREHOUSE_MODE=ducklake CUBEJS_DEV_MODE=false just serve-up`) |
| 4 | Переход file ↔ ducklake | §5 | `printenv WAREHOUSE_MODE` подтверждает режим; verify зелёной в обоих |
| 5 | Смена sf | §6: `just rebuild 2` / `just rebuild-lake 10` | числа масштабировались; verify зелёной; повторный rebuild-lake бакет не раздул |
| 6 | RBAC-демо (прод-контейнер) | `CUBEJS_DEV_MODE=false just serve-up` → `docs/cube-rbac.md` §«Руководство по проверке пользователем (пошагово)» | Admin видит всё; user — ровно 3 меры и только свой регион |
| 7 | MCP-агент | `docs/cube-mcp.md` §«Сценарии проверки MCP через AI-агента» (4 демо с эталонными числами) | все сценарии — совпадение чисел с эталонами |
