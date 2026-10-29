#!/usr/bin/env bash
# Генерация packages/evidence/sources/cube/connection.yaml из .env.
# Evidence 40.1.8 НЕ интерполирует ${VAR} в connection.yaml, поэтому креды
# подставляются рендером (сам файл с реальными секретами — вне git).
# Контейнер evidence рендерит connection.yaml сам (docker/evidence/entrypoint.sh);
# этот скрипт — только для запуска Evidence на хосте (docs/evidence-setup.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$REPO_ROOT/.env" ]; then set -a; . "$REPO_ROOT/.env"; set +a; fi

: "${CUBESQL_USER:?Не задан CUBESQL_USER — скопируйте .env.example → .env (docs/user-guide.md §1)}"
: "${CUBESQL_PASSWORD:?Не задан CUBESQL_PASSWORD — скопируйте .env.example → .env (docs/user-guide.md §1)}"

SRC="$REPO_ROOT/packages/evidence/sources/cube/connection.yaml.example"
DST="$REPO_ROOT/packages/evidence/sources/cube/connection.yaml"

sed -e "s/__CUBESQL_USER__/${CUBESQL_USER}/g" \
    -e "s/__CUBESQL_PASSWORD__/${CUBESQL_PASSWORD}/g" \
    "$SRC" > "$DST"
chmod 600 "$DST"
