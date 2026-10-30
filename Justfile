# pocketstack — демо-раннер. Полный план стадий: docs/plan.md
set dotenv-load # секреты из .env (см. .env.example); в коде кредов нет

python := "uv run"
duckdb_file := "warehouse/pocketstack.duckdb"

# Stage 1a: генерация TPC-H в схему raw_tpch; sf — параметр (default 1):
# just seed        → sf=1;   just seed 2 → sf=2;   just seed 0.1 → крохотный сет
seed sf="1":
    {{ python }} python packages/sqlmesh/seed_tpch.py {{ sf }}

# Stage 1: sqlmesh plan — интерактивный просмотр diff до применения
plan:
    cd packages/sqlmesh && {{ python }} sqlmesh plan

# Stage 1: sqlmesh apply — применение без промптов (CI-режим)
apply:
    cd packages/sqlmesh && {{ python }} sqlmesh plan --auto-apply --no-prompts

# Stage 7 (шаг 4): ducklake-режим — gateway lake (pg-каталог + MinIO; state в
# warehouse/lake_state.duckdb). Инфраструктура: docker compose up -d --wait
lake-init:
    docker compose run --rm minio-init

seed-lake sf="1":
    docker compose run --rm minio-init
    WAREHOUSE_MODE=ducklake {{ python }} python packages/sqlmesh/seed_tpch.py {{ sf }}

plan-lake:
    cd packages/sqlmesh && {{ python }} sqlmesh --gateway lake plan

apply-lake:
    cd packages/sqlmesh && {{ python }} sqlmesh --gateway lake plan --auto-apply --no-prompts

# Stage 7 (шаг 8→9): полный rebuild file-режима. Лок куба снимаем ОБЯЗАТЕЛЬНО
# (иначе Conflicting lock). Транзакционная замена БД (приём из stack.sh rebuild,
# удалённого на шаге 9): rename-бэкап → dbgen+sqlmesh → успех: бэкап удалить,
# сбой: авто-откат предыдущей БД. Evidence sources перематериализуем В КОНТЕЙНЕРЕ
# (кэш собран по старому sf).
rebuild sf="1":
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose stop cube
    db=warehouse/pocketstack.duckdb; bak=""
    if [ -e "$db" ]; then
        bak="$db.bak.$(date +%Y%m%d%H%M%S)"
        mv "$db" "$bak"
        [ -e "$db.wal" ] && mv "$db.wal" "$bak.wal" || true
        echo "бэкап текущей БД → $(basename "$bak")"
    fi
    if {{ python }} python packages/sqlmesh/seed_tpch.py {{ sf }} && ( cd packages/sqlmesh && {{ python }} sqlmesh plan --auto-apply --no-prompts ); then
        if [ -n "$bak" ]; then rm -f "$bak" "$bak.wal"; echo "успех: бэкап удалён"; fi
    else
        echo "ОШИБКА: сборка не удалась — откат предыдущей БД из бэкапа"
        rm -f "$db" "$db.wal"
        if [ -n "$bak" ]; then mv "$bak" "$db"; [ -e "$bak.wal" ] && mv "$bak.wal" "$db.wal" || true; fi
        exit 1
    fi
    docker compose --profile serve up -d --wait
    docker compose exec evidence npm run sources
    echo "rebuild sf={{ sf }} завершён (БД создана с нуля). Проверка: just verify"

# Stage 7 (шаг 8): полный rebuild ducklake-режима по процедуре «Смена sf»
# (docs/plan.md). Куб НЕ останавливаем — снапшот-изоляция каталога
# (zero-downtime swap; лок — только у pg-каталога, его держит транзакция).
# State sqlmesh сбрасывается ОТДЕЛЬНЫМ шагом (развязан с данными в lake).
# Финальный prune-only (--prune-old без sf) гасит time-travel ПОСЛЕ apply —
# снапшоты растут и от sqlmesh; так повторные rebuild бакет НЕ раздувает.
# Нужно time-travel для анализа (sf=1↔sf=10)? — прогоните шаги вручную
# (seed-lake / rm state / apply-lake) БЕЗ финальной чистки.
rebuild-lake sf="1":
    docker compose run --rm minio-init
    WAREHOUSE_MODE=ducklake {{ python }} python packages/sqlmesh/seed_tpch.py {{ sf }}
    rm -f warehouse/lake_state.duckdb warehouse/lake_state.duckdb.wal
    cd packages/sqlmesh && {{ python }} sqlmesh --gateway lake plan --auto-apply --no-prompts
    WAREHOUSE_MODE=ducklake {{ python }} python packages/sqlmesh/seed_tpch.py --prune-old

# Полный пересбор с нуля без бэкапа (warehouse детерминирован: dbgen + sqlmesh);
# sf — как в seed. ВНИМАНИЕ: перед reset снимите лок куба — `just cube-stop`
# (Cube держит блокировку DuckDB), иначе apply упадёт с Conflicting lock.
# Безопасный путь с бэкап-откатом — `just rebuild SF`.
reset sf="1":
    rm -f warehouse/pocketstack.duckdb warehouse/pocketstack.duckdb.wal
    {{ python }} python packages/sqlmesh/seed_tpch.py {{ sf }}
    cd packages/sqlmesh && {{ python }} sqlmesh plan --auto-apply --no-prompts

# Stage 1a+1b: тесты данных и витрины
test:
    {{ python }} pytest -q

# Stage 3: верификационный harness (golden-вопросы, rows/SQL-паритет, RBAC).
# Требует запущенного Cube: прод-контейнер `CUBEJS_DEV_MODE=false just serve-up`
# — RBAC-тесты работают только в прод-режиме; в dev (куб по умолчанию)
# они пропускаются (guard в test_rbac.py). Хостовый `just cube-prod` — опция.
# CUBEJS_DUCKDB_QUERY_LOG включает ground truth для `just verify`.
verify:
    HARNESS_STRICT=1 {{ python }} pytest packages/harness -q

# Stage 7 (шаг 6): verify в ducklake-режиме — Cube (WAREHOUSE_MODE=ducklake,
# прод) + ducklake-стек (docker compose up -d --wait, seed-lake, apply-lake)
verify-lake:
    WAREHOUSE_MODE=ducklake HARNESS_STRICT=1 {{ python }} pytest packages/harness -q

# Stage 7 (шаг 9): bench в ducklake-режиме (числа file/ducklake не смешиваются —
# docs/bench-protocol.md)
bench-lake:
    cd packages/harness && WAREHOUSE_MODE=ducklake {{ python }} python -m harness.bench

# Вариант A (Stage 7, шаг 7): serving в контейнерах (профиль serve: cube+evidence,
# + ducklake-инфраструктура). Секреты — env_file .env; MCP/harness — с хоста
# через published-порты 4000/15432 без изменений.
# Sources материализуем после старта: данные живут в слое контейнера и
# теряются при его пересоздании (как в rebuild, строка выше).
serve-up:
    docker compose --profile serve up -d --wait
    docker compose exec evidence npm run sources

# Снять serving (куб+evidence), НЕ трогая ducklake-инфраструктуру
serve-down:
    docker compose rm -sf cube evidence

# Остановить ducklake-инфраструктуру (pg-каталог + MinIO), НЕ трогая serving.
# Идемпотентно: если контейнеров нет — тихо выйдет без ошибки.
# Полная остановка стека одной парой just-команд:
# just serve-down && just infra-down
infra-down:
    @docker compose rm -sf postgres minio

# Снять лок Cube перед `just apply`/`reset` в file-режиме: контейнерный куб
# держит блокировку DuckDB, иначе sqlmesh упадёт «Conflicting lock is held in node»
cube-stop:
    docker compose stop cube

# Протокол оценки запросов (docs/bench-protocol.md): latency 3 путей + файлы SQL + сводная.
# Требует запущенного куба (контейнер `just serve-up` или хостовый `just cube`).
bench:
    cd packages/harness && {{ python }} python -m harness.bench

# Stage 2: cube-сервер (REST/GraphQL :4000 + SQL API :15432) в DEV-режиме
# (по умолчанию, packages/cube/.env: CUBEJS_DEV_MODE=true): playground
# http://localhost:4000 + hot-reload модели. Токены не проверяются; запрос
# БЕЗ токена получает admin (dev-фолбэк в contextToGroups, cube.js), с токеном
# access_policy применяется как в проде (docs/cube-rbac.md § Режимы сервера).
# CUBEJS_DUCKDB_QUERY_LOG включает ground truth для `just verify`.
cube:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{ justfile_directory() }}/artifacts/duckdb_query_log.csv npm start

# Синоним `just cube` (dev mode: playground на :4000).
cube-dev: cube

# ПРОД-режим: токены/учётки проверяются строго (сырой секрет → 403),
# безтокенный запрос отклоняется. RBAC-тесты `just verify` — только здесь.
cube-prod:
    mkdir -p artifacts
    cd packages/cube && CUBEJS_DUCKDB_QUERY_LOG={{ justfile_directory() }}/artifacts/duckdb_query_log.csv npm run prod

# Stage 4 → 7.1: Evidence — в контейнере (пин Node 20.19.0 внутри образа,
# docker/evidence/Dockerfile; системный 24.x ломает sveltekit/vite SSR —
# docs/gotchas.md «Установка/версии»). connection.yaml рендерится в entrypoint.
# Поднимает и cube (depends_on), + ducklake-инфраструктуру.
# + материализация sources (см. serve-up).
evidence:
    docker compose --profile serve up -d --wait evidence
    docker compose exec evidence npm run sources

# RBAC (docs/cube-rbac.md): JWT для ручных проверок REST под ролью.
# Стек ПО УМОЛЧАНИЮ работает под admin — токен user нужен только для сценария B.
# just token            → admin (по умолчанию);   just token user AFRICA
token group="admin" region="":
    @{{ python }} python scripts/make-cube-token.py --group {{ group }} {{ if region != "" { "--region " + region } else { "" } }}

# ВНИМАНИЕ: системный DuckDB CLI 2.0 — к файлам проекта ТОЛЬКО read-only.
# Запись/чекпойнт версией 2.0 сделает файл нечитаемым для 1.5.5 (Cube, Evidence, sqlmesh).
cli-readonly:
    duckdb -readonly {{ duckdb_file }}
