# pocketstack — демо-раннер. Полный план стадий: docs/plan.md
set dotenv-load := true  # секреты из .env (см. .env.example); в коде кредов нет

python := "uv run"
duckdb_file := "warehouse/pocketstack.duckdb"

# Stage 1a: генерация TPC-H в схему raw_tpch; sf — параметр (default 1):
#   just seed        → sf=1;   just seed 2 → sf=2;   just seed 0.1 → крохотный сет
seed sf="1":
    {{python}} python packages/sqlmesh/seed_tpch.py {{sf}}

# Stage 1: sqlmesh plan — интерактивный просмотр diff до применения
plan:
    cd packages/sqlmesh && {{python}} sqlmesh plan

# Stage 1: sqlmesh apply — применение без промптов (CI-режим)
apply:
    cd packages/sqlmesh && {{python}} sqlmesh plan --auto-apply --no-prompts

# Полный пересбор с нуля (warehouse детерминирован: dbgen + sqlmesh); sf — как в seed.
# ВНИМАНИЕ: перед reset остановите стек — Cube держит блокировку DuckDB
# (scripts/stack.sh down), иначе apply упадёт с Conflicting lock.
reset sf="1":
    rm -f warehouse/pocketstack.duckdb warehouse/pocketstack.duckdb.wal
    {{python}} python packages/sqlmesh/seed_tpch.py {{sf}}
    cd packages/sqlmesh && {{python}} sqlmesh plan --auto-apply --no-prompts

# Stage 1a+1b: тесты данных и витрины
test:
    {{python}} pytest -q

# Stage 3: верификационный harness (golden-вопросы, rows/SQL-паритет).
# Требует запущенного `just cube` (REST :4000 + SQL API :15432 + лог запросов DuckDB).
verify:
    HARNESS_STRICT=1 {{python}} pytest packages/harness -q

# Протокол оценки запросов (docs/bench-protocol.md): latency 3 путей + файлы SQL + сводная.
# Требует запущенного `just cube`.
bench:
    cd packages/harness && {{python}} python -m harness.bench

# Stage 2: cube-сервер (REST/GraphQL :4000 + SQL API :15432) в прод-режиме:
# RBAC (docs/cube-rbac.md) требует ВКЛЮЧЁННЫХ проверок авторизации —
# dev mode их отключает (каждый запрос = admin). CUBEJS_DUCKDB_QUERY_LOG
# включает ground truth для `just verify`.
cube:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{justfile_directory()}}/artifacts/duckdb_query_log.csv npm start

# То же в dev mode: playground + hot-reload модели на :4000.
# ВНИМАНИЕ: авторизация отключена → access_policy НЕ применяется.
cube-dev:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{justfile_directory()}}/artifacts/duckdb_query_log.csv npm run dev

# Stage 4: evidence dev-сервер (ТОЛЬКО Node 20: системный 24.x ломает sveltekit/vite SSR,
# см. docs/gotchas.md «Установка/версии»). connection.yaml рендерится из .env
evidence:
    scripts/render-evidence-connection.sh
    cd packages/evidence && PATH=$(HOME)/.local/opt/node-v20.19.0-linux-x64/bin:$(PATH) npm run dev

# ВНИМАНИЕ: системный DuckDB CLI 2.0 — к файлам проекта ТОЛЬКО read-only.
# Запись/чекпойнт версией 2.0 сделает файл нечитаемым для 1.4.4 (Cube, Evidence, sqlmesh).
cli-readonly:
    duckdb -readonly {{duckdb_file}}
