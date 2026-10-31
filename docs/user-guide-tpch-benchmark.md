# User guide: нативный TPC-H бенчмарк (№16)

Пошаговая инструкция воспроизведения. Реализация: `packages/harness/harness/tpch_native.py`,
запуск `just bench-native` (обёртка над `uv run python -m harness.tpch_native`).
Методика и интерпретация — `docs/bench-native-tpch.md`; контекст — `docs/plan.md` §9 №16.

## 1. Что это

22 запроса TPC-H (`tpch_queries()` из расширения tpch) к dbgen-данным **напрямую**,
без семантического слоя (Cube не участвует). Сравнивает физические раскладки одного
движка DuckDB 1.5.5:

- **file** — dbgen-файл `warehouse/tpch_native_sf<N>.duckdb`, нативные таблицы;
- **ducklake** — схема `tpch_native` в lake-каталоге (pg + parquet в MinIO), READ_ONLY.

Данные бенча **изолированы** от демо-витрины (`raw_tpch`, `marts` не читаются и не
пишутся): sf бенча независим от sf витрины. Валидация: паритет file ↔ ducklake
(построчно) + сверка с эталонами `tpch_answers()` (доступны для sf 0.01 / 0.1 / 1).

## 2. Предусловия

| Цель запуска | Что нужно |
|---|---|
| `--target file` | только uv-окружение репо (`uv sync`); docker НЕ нужен |
| `--target ducklake` / `both` | docker compose (pg-каталог + MinIO): `docker compose up -d --wait`; `.env` (раздел DuckLake, см. `.env.example`) |

## 3. Параметры CLI

| Параметр | Default | Описание |
|---|---|---|
| `sf` (позиционный) | `1` | scale factor dbgen: 0.01 / 0.1 / 1 / 10 / … |
| `--n` | `3` | итераций каждого запроса (статистика avg/min/max/p50) |
| `--target` | `both` | окружение: `file` \| `ducklake` \| `both` |
| `--queries` | все 22 | подмножество, напр. `'1,5,9'` |
| `--skip-answers` | выкл | не сверять с tpch_answers() |
| `--bootstrap-only` | — | только подготовка данных (без прогона) |

## 4. Пошаговый запуск

### Шаг 1 — быстрый смоук (sf=0.01, секунды)

```bash
just bench-native 0.01            # both-цели; нужен docker compose (ducklake)
# или без docker вообще:
cd packages/harness && uv run python -m harness.tpch_native 0.01 --target file
```

Первый запуск для sf делает **bootstrap** (дальше кэшируется по sf, повторный запуск
переиспользует): dbgen-файл `warehouse/tpch_native_sf0.01.duckdb` + CTAS в схему
lake `tpch_native`. Идемпотентно по маркеру sf (`tpch_native_meta`).

### Шаг 2 — канонический прогон (sf=1, эталоны answers доступны)

```bash
docker compose up -d --wait       # pg + minio (для ducklake-цели)
just bench-native 1               # ≈ 4 мин: bootstrap ~1.5 мин + 22×3 итерации × 2 цели
```

Ожидаемый результат: parity 22/22, answers 22/22 (см. §7 «Интерпретация»).

### Шаг 3 — только одно окружение

```bash
# file без docker (базлайн локального файла):
cd packages/harness && uv run python -m harness.tpch_native 1 --target file
# только lake-цель (данные уже забутстраплены на шаге 2 — переиспользуются):
cd packages/harness && uv run python -m harness.tpch_native 1 --target ducklake
```

Через `just`: `just bench-native 1` всегда both (упрощение обёртки); для
одиночной цели используйте прямую команду выше из `packages/harness`.

### Шаг 4 — другие sf / N / подмножество запросов

```bash
just bench-native 0.1                     # лёгкий прогон с answers-валидацией
just bench-native 10                      # тяжёлый: ~9 ГБ dbgen-файл, answers n/a
just bench-native 1 --n 5                 # 5 итераций на запрос (стабильнее p50)
just bench-native 1 --queries 1,5,9       # только Q1/Q5/Q9
just bench-native 1 --skip-answers        # без сверки эталонов (sf>1 не требуется)
```

Ориентиры по sf (масштаб линейный, машина — локальный docker):

| sf | dbgen-файл | bootstrap | прогон both (N=3) | answers |
|---|---|---|---|---|
| 0.01 | ~15 МБ | секунды | ~10 с | есть |
| 0.1 | ~30 МБ | ~10 с | ~20 с | есть |
| 1 | ~250 МБ | ~1.5 мин | ~4 мин | есть |
| 10 | ~9 ГБ | ~15 мин | ~30+ мин | n/a (эталоны до sf=1) |

### Шаг 5 — только подготовка данных (без прогона)

```bash
just bench-native 10 --bootstrap-only     # забутстрапить заранее, прогон позже
```

## 5. Результаты (формат ducklake-sandbox + блок параметров)

Один прогон → `results/native/<timestamp>/`:

| Файл | Содержимое |
|---|---|
| `benchmark_detailed_timing.csv` | каждая попытка: `query,target,attempt,time_ms,rows,status` |
| `benchmark_summary.csv` | `query × target`: `iterations, avg/min/max/p50/total_time_ms, rows, status` |
| `validation_summary.csv` | `query, parity(, reason), answers(, reason)` |
| `tpch_all_queries.sql` | все 22 запроса дословно (референс прогона) |
| `summary.md` | ОДНА таблица Q1–Q22 file vs ducklake + **блок «Параметры прогона»** (sf, N, target, запросы, answers, duckdb, commit, запуск) + итог Σ/медиана |

Журнал прогонов: `results/native/index.md` — накапливается (run, commit, sf, N,
target, parity, answers, Σp50 по целям). Каждый прогон коммитится — это журнал проекта.

Пример блока параметров в `summary.md`:

```
## Параметры прогона

| Параметр | Значение |
|---|---|
| запуск | 2026-10-31T164932 |
| commit | `d8e8a50` |
| sf | 1 |
| итераций на запрос (N) | 3 |
| цель | file + ducklake |
| запросы | Q1–Q22 (22) |
| answers (tpch_answers) | вкл (sf=1) |
| duckdb | 1.5.5 |
```

## 6. Правила сравнения

- Сравнивать прогоны **только внутри одного sf** (данные детерминированы — dbgen).
- `--target file` и `--target both` для file-колонок сопоставимы (один dbgen-файл).
- answers `n/a` для sf>1 — эталоны `tpch_answers()` существуют только для sf ≤ 1.
- Сравнение с `just bench` (сквозной через куб) некорректно — там другие вопросы и пути.

## 7. Интерпретация (базлайн sf=1)

Σp50 file ~310 / ducklake ~750 мс на 22 запроса; медиана p50 ~11 / ~31 мс.
ducklake ≈ 2–2.5× дороже — каждая выборка тянет parquet из MinIO (S3-hop);
у ducklake p50 ≈ min — итерации идут по прогретому кэшу. Тяжелейшие для file:
Q9/Q21 (полный скан lineitem). Подробности — `docs/bench-native-tpch.md` §4.

## 8. Чистка / диск

- dbgen-файлы живут в `warehouse/` (gitignored): `rm warehouse/tpch_native_sf*.duckdb`
  — при следующем запуске регенерируются автоматически.
- lake-схема `tpch_native` в общем pg-каталоге/бакете; `rebuild-lake` её НЕ чистит.
  Полная зачистка: `DROP SCHEMA pocketstack.tpch_native CASCADE` (сессия с
  `lake_attach(alias='pocketstack')`), либо вместе с бакетом через rebuild-инфраструктуру.
- ВНИМАНИЕ: системный DuckDB CLI 2.0 к dbgen-файлам не подключать на запись
  (правило проекта: только `just cli-readonly`).

## 9. Диагностика

| Симптом | Причина / решение |
|---|---|
| `Не задана переменная DUCKLAKE_...` | `.env` не скопирован/не заполнен (`cp .env.example .env`) |
| Ошибка подключения pg/minio | `docker compose up -d --wait`; проверка: `docker compose ps` |
| bootstrap заново гоняет dbgen | маркер sf не совпал (файл/схема другого sf) — это норма при смене sf |
| `Catalog "pocketstack" does not exist` | attach без алиаса; в коде используйте `lake_attach(con, alias="pocketstack")` |
| answers FAIL при ручных правках запросов | сверяются эталонные `tpch_queries()` дословно; правки — только через `--queries` выбор номера |
