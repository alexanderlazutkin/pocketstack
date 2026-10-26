# pocketstack

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![tests](https://img.shields.io/badge/tests-117%20%E2%9C%94-brightgreen)](#проверки)
[![verify](https://img.shields.io/badge/harness%20verify-69%2F69-brightgreen)](#проверки)

Демонстрационный стек локальной аналитики: **TPC-H → DuckDB → sqlmesh → Cube → Evidence**
с верификационным harness'ом (TDD), протоколом оценки производительности запросов
и **MCP-сервером для AI-агентов** поверх семантического слоя.
Всё работает на одной машине, без внешних сервисов.

Репозиторий: <https://github.com/alexanderlazutkin/pocketstack>.

## Цели

1. Показать воспроизводимый, проверяемый локальный data-стек на примере масштабируемых
   данных теста [TPC-H](https://tpc.org/tpch/):
   генерация данных → витрина (звезда) → семантический слой → BI.
2. Единый источник метрик: **вся логика метрик — в Cube** (ROLAP-семантический слой
   над витриной в DuckDB); BI-дашборды — только отображение поверх Cube;
   сложные отклонения (YoY/PoP) — в кубах, а не в дашбордах.
3. Доказуемость цифр: harness из 13 golden-вопросов сверяет три пути
   (Cube REST ↔ SQL API ↔ эталонный SQL к витрине) + лог выполнения DuckDB.
4. AI-агент без «галлюцинаций»: использует описание метаданных в Cube на русском, агент работает через MCP с
   метриками и объясняет формулы по сгенерированному SQL, а не по памяти.

## Архитектура

```
┌──────────────────────────── Данные ────────────────────────────┐
│                                                                 │
│  TPC-H dbgen (sf=N) ──▶ sqlmesh ──▶ DuckDB                      │
│  (генерация данных)     (витрина-    raw_tpch → marts.*         │
│                          звезда)      fact_sales + dim_*        │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────── Семантический слой ─────────────────────┐
│  Cube (OSS): view `sales` · куб `sales_mov` (YoY/PoP)           │
│  ├─ REST / GraphQL API ── :4000                                 │
│  └─ SQL API (pg-wire) ───── :15432                              │
└─────────────────────────────────────────────────────────────────┘
         │                   │                       │
         ▼                   ▼                       ▼
  Evidence BI :3000    SQL-клиенты           pocketstack-mcp (stdio)
  (6 страниц,         (DBeaver / DBX)        cube_meta · cube_load ·
  DuckDB-WASM)                                 cube_sql · sql_api
                                                        │
                                                        ▼
                                                 AI-агент (opencode /
                                                 Claude Code)

  harness ─ 13 golden-вопросов ─▶ REST ↔ SQL API ↔ эталонный SQL + лог DuckDB
```

- **Данные**: TPC-H dbgen (масштабируемый объём, `sf`) → sqlmesh строит витрину-звезду в DuckDB.
- **Семантика**: Cube — view `sales`, куб `sales_mov` (YoY/PoP-отклонения), KPI-measures;
  каждый куб/член описан по-русски (`title`/`description` — AI-context).
- **BI**: Evidence — 6 страниц: выручка, отклонения, клиенты, доставка,
  верификация (13 golden-вопросов на одной странице).
- **SQL-клиенты**: любой pg-клиент через SQL API :15432 — живая семантика без Cube UI.
- **AI-агент**: pocketstack-mcp — тонкий MCP-сервер (FastMCP, stdio) поверх Cube:
  `cube_meta` / `cube_load` / `cube_sql` / `sql_api`, все read-only.
- **Проверки**: harness — parity/determinism/ground-truth тесты, bench.

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

Подключить AI-агента (opencode/Claude Code) к семантическому слою:

```bash
opencode mcp add cube -- uv run --directory /путь/к/pocketstack python -m cube_mcp
```

Сценарии проверки агента (4 демо с эталонными числами sf=1) — `docs/cube-mcp.md` §«Сценарии».

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
| `docs/cube-mcp.md` | MCP-сервер Cube для AI-агентов: семантика на русском, 4 сценария проверки, подключение |
| `docs/cube-sql-clients.md` | DBeaver/DBX к SQL API Cube |
| `docs/cube-oss-vs-enterprise.md` | Cube OSS vs Enterprise: что есть в self-hosted, лимиты Cloud, OSS-альтернативы |
| `docs/bi-tools-comparison.md` | сравнение BI-инструментов (выбор Evidence) |
| `docs/bench-protocol.md` | протокол оценки запросов |
| `docs/gotchas.md` | нюансы и грабли: симптом → причина → решение |

Skills для AI-агента (правила работы с кубами pocketstack через MCP):
`.opencode/skills/` — `cube-explore-model`, `cube-build-model`, `cube-run-query`.

## Управление стеком

`scripts/stack.sh up|down|status|restart|sources|rebuild [sf]` —
полное описание: `scripts/stack.sh` (без аргументов) или `docs/user-guide.md`.

## Проверки

`just test` — 117 тестов (модель, harness, MCP: unit + e2e);
`just verify` — 69 проверок живого стека (REST ↔ SQL API ↔ reference ↔ ground truth);
итог — `artifacts/verify-report.md` (13/13 по всем осям).

## Статусы стадий

Stage 0–5 завершены (✅ 2026-10-25/26, см. `docs/plan.md` §5): окружение, витрина,
семантика, harness, BI, MCP-интерактив. Далее: Stage 6 (DuckDB 2.0), 7 (ducklake+MinIO).
