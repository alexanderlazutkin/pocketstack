# pocketstack — демо-раннер. Полный план стадий: docs/plan.md
python := "uv run"
duckdb_file := "warehouse/pocketstack.duckdb"

# Stage 1a: генерация TPC-H sf=1 в схему raw_tpch
seed:
    {{python}} python packages/sqlmesh/seed_tpch.py

# Stage 1: sqlmesh plan (посмотреть diff до применения)
plan:
    cd packages/sqlmesh && {{python}} sqlmesh plan --no-prompts

# Stage 1: sqlmesh apply
apply:
    cd packages/sqlmesh && {{python}} sqlmesh apply

# Stage 1a+1b: тесты данных и витрины
test:
    {{python}} pytest -q

# Stage 3: верификационный harness (golden-вопросы, rows/SQL-паритет)
verify:
    {{python}} pytest packages/harness -q

# Stage 2: cube dev-сервер (REST/GraphQL :4000 + SQL API :15432)
cube:
    cd packages/cube && npm run dev

# Stage 4: evidence dev-сервер
evidence:
    cd packages/evidence && npm run dev

# ВНИМАНИЕ: системный DuckDB CLI 2.0 — к файлам проекта ТОЛЬКО read-only.
# Запись/чекпойнт версией 2.0 сделает файл нечитаемым для 1.4.4 (Cube, Evidence, sqlmesh).
cli-readonly:
    duckdb -readonly {{duckdb_file}}
