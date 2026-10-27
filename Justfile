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

# Stage 3: верификационный harness (golden-вопросы, rows/SQL-паритет, RBAC).
# Требует запущенного Cube: `just cube-prod` — RBAC-тесты работают только
# в прод-режиме; в dev (`just cube`) они пропускаются (guard в test_rbac.py).
verify:
    HARNESS_STRICT=1 {{python}} pytest packages/harness -q

# Протокол оценки запросов (docs/bench-protocol.md): latency 3 путей + файлы SQL + сводная.
# Требует запущенного `just cube`.
bench:
    cd packages/harness && {{python}} python -m harness.bench

# Stage 2: cube-сервер (REST/GraphQL :4000 + SQL API :15432) в DEV-режиме
# (по умолчанию, packages/cube/.env: CUBEJS_DEV_MODE=true): playground
# http://localhost:4000 + hot-reload модели. Токены не проверяются; запрос
# БЕЗ токена получает admin (dev-фолбэк в contextToGroups, cube.js), с токеном
# access_policy применяется как в проде (docs/cube-rbac.md § Режимы сервера).
# CUBEJS_DUCKDB_QUERY_LOG включает ground truth для `just verify`.
cube:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{justfile_directory()}}/artifacts/duckdb_query_log.csv npm start

# Синоним `just cube` (dev mode: playground на :4000).
cube-dev: cube

# ПРОД-режим: токены/учётки проверяются строго (сырой секрет → 403),
# безтокенный запрос отклоняется. RBAC-тесты `just verify` — только здесь.
cube-prod:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{justfile_directory()}}/artifacts/duckdb_query_log.csv npm run prod

# Stage 4: evidence dev-сервер (ТОЛЬКО Node 20: системный 24.x ломает sveltekit/vite SSR,
# см. docs/gotchas.md «Установка/версии»). connection.yaml рендерится из .env
evidence:
    scripts/render-evidence-connection.sh
    cd packages/evidence && PATH=$(HOME)/.local/opt/node-v20.19.0-linux-x64/bin:$(PATH) npm run dev

# RBAC (docs/cube-rbac.md): JWT для ручных проверок REST под ролью.
# Стек ПО УМОЛЧАНИЮ работает под admin — токен user нужен только для сценария B.
#   just token            → admin (по умолчанию);   just token user AFRICA
token group="admin" region="":
    @{{python}} python scripts/make-cube-token.py --group {{group}} {{ if region != "" { "--region " + region } else { "" } }}

# ВНИМАНИЕ: системный DuckDB CLI 2.0 — к файлам проекта ТОЛЬКО read-only.
# Запись/чекпойнт версией 2.0 сделает файл нечитаемым для 1.4.4 (Cube, Evidence, sqlmesh).
cli-readonly:
    duckdb -readonly {{duckdb_file}}
