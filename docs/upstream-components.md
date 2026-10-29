# Реестр сторонних компонентов: пины и кодовые отклонения

> Аудит шага 9.1 (2026-10-29): подтверждение, что стек собирается из
> **непатченных апстрим-релизов**. Любой компонент заменяем на официальную
> сборку той же версии без форков и патчей.

## Правила классификации

- **Кодовое отклонение** = правка кода стороннего пакета, форк, vendored-копия
  с изменениями, локальный бинарник. В реестр входят только они.
- **НЕ отклонение**: конфигурация (`.env`, YAML-модели, compose, Dockerfile'ы,
  набор зависимостей и npm-`overrides` как версии-пины) и **собственный код**
  проекта (обёртки, MCP-сервер, harness, модели — отдельный список ниже).

## Реестр: компонент → пин → отклонения

| # | Компонент | Пин | Источник | Кодовые отклонения |
|---|---|---|---|---|
| 1 | DuckDB (python: sqlmesh, harness, seed) | `==1.5.5` | PyPI (`uv.lock`) | **0** |
| 2 | `@duckdb/node-api` — движок куба-контейнера | `1.5.5-r.5` (из lock) | npm | **0** |
| 3 | Расширение `tpch` | `v1.5.5` | офиц. репо расширений DuckDB (`INSTALL`, режим REPOSITORY) | **0** |
| 4 | Расширение `ducklake` | `d8a1881e` | там же | **0** |
| 5 | Расширение `httpfs` | `827222f` | там же | **0** |
| 6 | Расширение `postgres` | по движку 1.5.5 | там же | **0** |
| 7 | Cube backend: `@cubejs-backend/server` + `-server/duckdb-driver` | `^1.8.13` (lock) | npm | **0** — `packages/cube/package.json` = апстрим-шаблон `docker` 1.8.13 без правок |
| 8 | sqlmesh | `==0.236.4` | PyPI | **0** — `pocketstack-sqlmesh` наш отдельный пакет, не форк |
| 9 | Evidence (`@evidence-dev/*`) | `^40.1.8` + deps по lock | npm | **0** — package.json = апстрим-шаблон `legacy`: блок `overrides` (jsonwebtoken/trim/sqlite3/axios) — **дословно из шаблона**; `scripts/update-evidence-packages.js` — файл шаблона (коммит клонирования, не менялся). Добавлены только dev-инструменты (`puppeteer-core` для `visual-check`, `autoprefixer`, `@sveltejs/vite-plugin-svelte`) — добавление зависимостей ≠ правка кода Evidence |
| 10 | PostgreSQL (каталог ducklake) | образ `postgres:17-alpine` | Docker Hub (офиц.) | **0** |
| 11 | MinIO (+ mc) | `elestio/minio@sha256:25348a25…` (digest) | Docker Hub | **0** — внутри официальный бинарник `RELEASE.2025-09-07T16-13-09Z` (commit-id в `--version`) + bundled mc; `minio/minio` удалён с Hub (см. docker-compose.yml) |
| 12 | Node-образы | `node:24-bookworm` (cube), `node:20.19.0-bookworm` (evidence) | Docker Hub (офиц.) | **0** |
| 13 | FastMCP (MCP-сервер) | по `uv.lock` | PyPI | **0** |

**Итог: 0 кодовых отклонений.** Версия расширений неявно пинится движком 1.5.5
(единая версия для всех клиентов — матрица совместимости, `docs/gotchas.md`).

## Как проверяли (воспроизводимые проверки)

```bash
# vendored-бинарники/патчи в git — пусто
git ls-files | grep -E '\.patch$|\.diff$|patches/|\.so$|\.wasm$|\.duckdb_extension$'

# node_modules не в git; npm-патчей и postinstall-хуков нет
git ls-files | grep -c node_modules                     # 0
grep -l patchedDependencies packages/*/package-lock.json # пусто
grep -n postinstall\|patch-package packages/*/package.json # пусто

# python: все пакеты из PyPI, без [tool.uv.patch] и path/git-депов
grep -c 'tool.uv.patch' uv.lock                          # 0

# Dockerfile'ы: только COPY нашего кода + npm ci (нет sed/patch апстрима)
grep -rn 'sed \|patch\|apt-get' docker/

# версии расширений и MinIO
uv run python -c "import duckdb; ..."   # duckdb_extensions(): REPOSITORY
docker run --rm --entrypoint /bin/sh elestio/minio@sha256:253... -c 'minio --version'
```

## Собственный слой (не является правками компонентов)

| Слой | Что там |
|---|---|
| `packages/cube/cube.js` | обёртка сервера: `TimingDuckDBDriver` (сабкласс офиц. `DuckDBDriver`: ATTACH ducklake/SET s3/лог запросов), `contextToGroups`/`checkSqlAuth` (RBAC) |
| `packages/cube/model/**` | семантические модели (view `sales`, `sales_mov`, dim-кубы, `access_policy`) |
| `packages/sqlmesh/**` | `pocketstack-sqlmesh`: `seed_tpch.py` (dbgen → file/lake, `--prune-old`) + модели витрины-звезды |
| `packages/harness/**` | верификационный harness: golden-вопросы, клиенты REST/SQL API, ground truth, bench, токены |
| `packages/mcp/**` | `pocketstack-mcp`: FastMCP-обёртка над Cube (read-only) |
| `packages/evidence/{pages,sources}/**` | контент дашбордов (SQL sources = golden-SQL дословно) |
| `docker/**`, `docker-compose.yml`, `Justfile`, `scripts/**` | сборка образов, оркестрация, утилиты (токены, рендер кред, стресс-тест) |
| `.env.example` | шаблон конфигурации (секреты — вне git) |

## Следствия

- Обновление любого компонента = смена пина на апстрим-релиз (плюс прогон
  `just test` / `verify`); патчей применять не нужно.
- Воспроизводимость: `uv sync` + `npm ci` + `docker compose build` дают
  идентичное окружение из одних lock-файлов.
