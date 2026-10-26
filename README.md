# pocketstack

Демонстрационный стек локальной аналитики: **TPC-H → DuckDB → sqlmesh → Cube → Evidence**
с верификационным harness'ом (TDD) и протоколом оценки производительности запросов.
Всё работает на одной машине, без внешних сервисов.

## Цели

1. Показать воспроизводимый, верифицируемый локальный data-стек «мини-предприятие»:
   генерация данных → витрина (звезда) → семантический слой → BI.
2. Единый источник метрик: **вся логика метрик — в Cube** (семантический слой),
   BI только показывает; сложные отклонения (YoY/PoP) — в кубах, а не в дашбордах.
3. Доказуемость цифр: harness из 13 golden-вопросов сверяет три пути
   (Cube REST ↔ SQL API ↔ эталонный SQL к витрине) + ground truth из лога DuckDB.

## Архитектура

```
                 dbgen(sf=N)                sqlmesh (витрина-звезда)
 TPC-H ─────────────────────▶ raw_tpch ──────────────────────────▶ marts.*
 (duckdb ext)                (схема DuckDB)                    fact_sales + dim_*
                                                                    │
                              packages/pocketstack.duckdb ◀─────────┘
                                    ▲                    ▲
                          sqlmesh (write)         Cube dev :4000 (REST/GraphQL)
                                                  Cube SQL API :15432 (pg-wire)
                                                        │
                              Evidence :3000 ────────────┘ (материализация parquet,
                              (DuckDB-WASM в браузере)     рантайм от Cube не зависит)

 SQL-клиенты (DBeaver/DBX) ──:15432──▶ Cube (живая семантика)
 harness: 13 golden-вопросов ─▶ REST + SQL API + эталонный SQL + лог DuckDB
```

- **Слой данных**: `packages/sqlmesh` — seed TPC-H (параметр `sf`), модели витрины.
- **Семантика**: `packages/cube` — view `sales`, куб `sales_mov` (YoY/PoP-отклонения),
  KPI-measures. SQL API для любых pg-клиентов.
- **BI**: `packages/evidence` — 6 страниц: выручка, отклонения, клиенты, доставка,
  верификация (13 golden-вопросов на одной странице).
- **Проверки**: `packages/harness` — parity/determinism/ground-truth тесты, bench.

## Быстрый старт

```bash
# 0) предусловия: uv (python 3.12), Node 20 (см. docs/evidence-setup.md §0), just
cp .env.example .env && $EDITOR .env   # секреты (openssl rand -hex 32) — вне git
uv sync                                                    # python-окружение
cd packages/evidence && npm ci --legacy-peer-deps && cd .. # BI-пакет

scripts/stack.sh rebuild          # БД с нуля (sf=1) + витрины + стек + sources
# или по шагам: just seed && just apply && scripts/stack.sh up && scripts/stack.sh sources

just verify                       # 69 тестов: паритет 3 путей (нужен запущенный стек)
just bench                        # 13 вопросов, latency 3 путей
```

Открыть: **Evidence** http://localhost:3000 · **Cube UI** http://localhost:4000 ·
SQL-клиенты — `docs/cube-sql-clients.md`.

Другой объём данных: `scripts/stack.sh rebuild 2` (sf=2) или `just seed 0.1`.

## Безопасность

- Креды/токены — только в `.env` (в git не попадает; шаблон `.env.example`).
  Код не содержит секретов и фолбэков: без `.env` компоненты не стартуют.
- `connection.yaml` Evidence с реальными кредами генерируется из `.env`
  (`scripts/render-evidence-connection.sh`) и тоже вне git.
- Известное ограничение: Cube dev слушает все интерфейсы (0.0.0.0, опции привязки
  в dev-сервере Cube нет) — запускайте только на доверенной машине/за файрволом.

## Документация

| Документ | Что внутри |
|---|---|
| `docs/user-guide.md` | **руководство пользователя**: установка, запуск, разблокировка DuckDB, сценарий сверки |
| `docs/plan.md` | план стадий (со статусами) + реестр вопросов |
| `docs/evidence-setup.md` | Evidence: установка с нуля (runbook) |
| `docs/cube-sql-clients.md` | DBeaver/DBX к SQL API Cube |
| `docs/bench-protocol.md` | протокол оценки запросов |
| `docs/gotchas.md` | нюансы и грабли: симптом → причина → решение |

## Управление стеком

`scripts/stack.sh up|down|status|restart|sources|rebuild [sf]` —
полное описание: `scripts/stack.sh` (без аргументов) или `docs/user-guide.md`.

## Статусы стадий

Stage 0–4 завершены (✅ 2026-10-25/26, см. `docs/plan.md` §5): окружение, витрина,
семантика, harness, BI. Далее: Stage 5 (MCP-интерактив), 6 (DuckDB 2.0), 7 (ducklake+MinIO).
