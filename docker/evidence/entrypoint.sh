#!/usr/bin/env bash
# connection.yaml из env: Evidence 40.1.8 не интерполирует ${VAR} (docs/gotchas.md).
# Креды приходят переменными окружения (env_file .env в docker-compose);
# файл с секретами живёт только внутри контейнера (chmod 600, не в образ/git).
set -euo pipefail

: "${CUBESQL_USER:?задайте CUBESQL_USER (env_file .env)}"
: "${CUBESQL_PASSWORD:?задайте CUBESQL_PASSWORD (env_file .env)}"

cat > sources/cube/connection.yaml <<EOF
name: cube
type: postgres
description: Cube semantic layer через SQL API (pg-wire) — рендер entrypoint контейнера
options:
  host: ${CUBESQL_HOST:-cube}
  port: ${CUBESQL_PORT:-15432}
  user: ${CUBESQL_USER}
  password: ${CUBESQL_PASSWORD}
  database: default
EOF
chmod 600 sources/cube/connection.yaml

# duckdb_local — ХОСТОВОЙ debug-коннектор (прямое чтение файла витрины,
# docs/evidence-setup.md). В контейнере его нет (пути хоста + дизайн Stage 7:
# Evidence читает ТОЛЬКО через Cube SQL API), а его connection.yaml с путями
# хоста роняет `npm run sources`. Запросов/страниц у источника нет — просто
# выключаем в рантайме.
rm -f sources/duckdb_local/connection.yaml

exec "$@"
