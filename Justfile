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

# Stage 7 (шаг 4): ducklake-режим — gateway lake (pg-каталог + MinIO; state в
# warehouse/lake_state.duckdb). Инфраструктура: docker compose up -d --wait
seed-lake sf="1":
    WAREHOUSE_MODE=ducklake {{python}} python packages/sqlmesh/seed_tpch.py {{sf}}

plan-lake:
    cd packages/sqlmesh && {{python}} sqlmesh --gateway lake plan

apply-lake:
    cd packages/sqlmesh && {{python}} sqlmesh --gateway lake plan --auto-apply --no-prompts

# Stage 7 (шаг 8): полный rebuild file-режима (контейнерный аналог stack.sh
# rebuild; судьба stack.sh — шаг 9 ревью). Лок куба снимаем ОБЯЗАТЕЛЬНО
# (иначе Conflicting lock); Evidence sources перематериализуем В КОНТЕЙНЕРЕ
# (кэш собран по старому sf). Аварийное восстановление не нужно: seed+apply
# идемпотентны, старый файл удаляется явно (бэкап не храним — детерминизм).
rebuild sf="1":
    docker compose stop cube
    rm -f warehouse/pocketstack.duckdb warehouse/pocketstack.duckdb.wal
    {{python}} python packages/sqlmesh/seed_tpch.py {{sf}}
    cd packages/sqlmesh && {{python}} sqlmesh plan --auto-apply --no-prompts
    docker compose --profile serve up -d --wait
    docker compose exec evidence npm run sources

# Stage 7 (шаг 8): полный rebuild ducklake-режима по процедуре «Смена sf»
# (docs/plan.md). Куб НЕ останавливаем — снапшот-изоляция каталога
# (zero-downtime swap; лок — только у pg-каталога, его держит транзакция).
# State sqlmesh сбрасывается ОТДЕЛЬНЫМ шагом (развязан с данными в lake).
# Финальный prune-only (--prune-old без sf) гасит time-travel ПОСЛЕ apply —
# снапшоты растут и от sqlmesh; так повторные rebuild бакет НЕ раздувает.
# Нужно time-travel для анализа (sf=1↔sf=10)? — прогоните шаги вручную
# (seed-lake / rm state / apply-lake) БЕЗ финальной чистки.
rebuild-lake sf="1":
    WAREHOUSE_MODE=ducklake {{python}} python packages/sqlmesh/seed_tpch.py {{sf}}
    rm -f warehouse/lake_state.duckdb warehouse/lake_state.duckdb.wal
    cd packages/sqlmesh && {{python}} sqlmesh --gateway lake plan --auto-apply --no-prompts
    WAREHOUSE_MODE=ducklake {{python}} python packages/sqlmesh/seed_tpch.py --prune-old

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
# Требует запущенного Cube: прод-контейнер `CUBEJS_DEV_MODE=false just serve-up`
# — RBAC-тесты работают только в прод-режиме; в dev (куб по умолчанию)
# они пропускаются (guard в test_rbac.py). Хостовый `just cube-prod` — опция.
# CUBEJS_DUCKDB_QUERY_LOG включает ground truth для `just verify`.
verify:
    HARNESS_STRICT=1 {{python}} pytest packages/harness -q

# Stage 7 (шаг 6): verify в ducklake-режиме — Cube (WAREHOUSE_MODE=ducklake,
# прод) + ducklake-стек (docker compose up -d --wait, seed-lake, apply-lake)
verify-lake:
    WAREHOUSE_MODE=ducklake HARNESS_STRICT=1 {{python}} pytest packages/harness -q

# Stage 7 (шаг 9): bench в ducklake-режиме (числа file/ducklake не смешиваются —
# docs/bench-protocol.md)
bench-lake:
    cd packages/harness && WAREHOUSE_MODE=ducklake {{python}} python -m harness.bench

# Вариант A (Stage 7, шаг 7): serving в контейнерах (профиль serve: cube+evidence,
# + ducklake-инфраструктура). Секреты — env_file .env; MCP/harness — с хоста
# через published-порты 4000/15432 без изменений.
serve-up:
    docker compose --profile serve up -d --wait

# Снять serving (куб+evidence), НЕ трогая ducklake-инфраструктуру
serve-down:
    docker compose rm -sf cube evidence

# Снять лок Cube перед `just apply`/`reset` в file-режиме (аналог `stack.sh down`
# для контейнерного куба): иначе sqlmesh упадёт «Conflicting lock is held in node»
cube-stop:
    docker compose stop cube

# Протокол оценки запросов (docs/bench-protocol.md): latency 3 путей + файлы SQL + сводная.
# Требует запущенного куба (контейнер `just serve-up` или хостовый `just cube`).
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

# Stage 4 → 7.1: Evidence — в контейнере (пин Node 20.19.0 внутри образа,
# docker/evidence/Dockerfile; системный 24.x ломает sveltekit/vite SSR —
# docs/gotchas.md «Установка/версии»). connection.yaml рендерится в entrypoint.
# Поднимает и cube (depends_on), + ducklake-инфраструктуру.
evidence:
    docker compose --profile serve up -d --wait evidence

# RBAC (docs/cube-rbac.md): JWT для ручных проверок REST под ролью.
# Стек ПО УМОЛЧАНИЮ работает под admin — токен user нужен только для сценария B.
#   just token            → admin (по умолчанию);   just token user AFRICA
token group="admin" region="":
    @{{python}} python scripts/make-cube-token.py --group {{group}} {{ if region != "" { "--region " + region } else { "" } }}

# ВНИМАНИЕ: системный DuckDB CLI 2.0 — к файлам проекта ТОЛЬКО read-only.
# Запись/чекпойнт версией 2.0 сделает файл нечитаемым для 1.5.5 (Cube, Evidence, sqlmesh).
cli-readonly:
    duckdb -readonly {{duckdb_file}}
