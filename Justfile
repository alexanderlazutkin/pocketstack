# pocketstack — демо-раннер. Полный план стадий: docs/plan.md
python := "uv run"
duckdb_file := "warehouse/pocketstack.duckdb"

# Stage 1a: генерация TPC-H sf=1 в схему raw_tpch
seed:
    {{python}} python packages/sqlmesh/seed_tpch.py

# Stage 1: sqlmesh plan — интерактивный просмотр diff до применения
plan:
    cd packages/sqlmesh && {{python}} sqlmesh plan

# Stage 1: sqlmesh apply — применение без промптов (CI-режим)
apply:
    cd packages/sqlmesh && {{python}} sqlmesh plan --auto-apply --no-prompts

# Полный пересбор с нуля: warehouse детерминирован (dbgen + sqlmesh)
reset:
    rm -f warehouse/pocketstack.duckdb warehouse/pocketstack.duckdb.wal
    {{python}} python packages/sqlmesh/seed_tpch.py
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

# Stage 2: cube dev-сервер (REST/GraphQL :4000 + SQL API :15432).
# CUBEJS_DUCKDB_QUERY_LOG включает ground truth для `just verify`.
cube:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{justfile_directory()}}/artifacts/duckdb_query_log.csv npm run dev

# Stage 4: evidence dev-сервер
evidence:
    cd packages/evidence && npm run dev

# ВНИМАНИЕ: системный DuckDB CLI 2.0 — к файлам проекта ТОЛЬКО read-only.
# Запись/чекпойнт версией 2.0 сделает файл нечитаемым для 1.4.4 (Cube, Evidence, sqlmesh).
cli-readonly:
    duckdb -readonly {{duckdb_file}}
