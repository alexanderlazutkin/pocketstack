# RBAC в Cube OSS: access_policy + группы из JWT (Admin vs User)

> Per-role доступ к семантическому слою pocketstack на чистом Cube OSS
> (framework access policies, PR cube-js/cube.js#8766 — в OSS с конца 2024).
> Enterprise отличается только UI/CLI-управлением ролями — сам механизм в OSS.
> Демо: **admin видит всё; user — ровно 3 меры и только свой регион**, на всех
> инструментах: REST, SQL API, MCP.

## Модель доступа

```
┌─────────────────────── Кто ───────────────────────┐
│ REST :4000      JWT (scripts/make-cube-token.py)  │
│                 claims: { groups, region }        │
│ SQL API :15432  учётка (checkSqlAuth в cube.js)   │
│                 admin | pocketstack_user           │
└──────────────┬────────────────────────────────────┘
               ▼
      contextToGroups(context)          ← cube.js
               ▼  группы: [admin] | [user]
┌────────────── Что разрешено ──────────────────────┐
│ access_policy (views/sales.view.yml, кубы):       │
│  member_level — какие меры/измерения              │
│  row_level    — какие строки (регион)             │
└───────────────────────────────────────────────────┘
```

| Группа | Меры витрины `sales` | Строки |
| --- | --- | --- |
| `admin` | все 6 (вкл. `avg_discount`) | все регионы |
| `user` | **ровно 3**: `revenue`, `quantity`, `orders_count` | только `securityContext.region` (claim токена / учётки) |
| прочие | — | **deny by default** |

Прямые кубы `fact_sales`/`sales_mov` для user закрыты (политики: admin + `*`-deny),
`sales_mov` (YoY/PoP) — только admin. Справочники `dim_*` без политик (reference data).

## Где что живёт

| Файл | Роль |
| --- | --- |
| `packages/cube/cube.js` | `contextToGroups` (группы из подписанных claims), `checkSqlAuth` (per-role учётки SQL API), `pgSqlPort`, `cacheAndQueueDriver: 'memory'` |
| `packages/cube/model/views/sales.view.yml` | `access_policy` витрины: admin всё; user 3 меры + `row_level` по `customer_region` |
| `packages/cube/model/cubes/fact_sales.cube.yml` | факт только через витрину (см. «Подводные камни»); admin — всё |
| `packages/cube/model/cubes/sales_mov.cube.yml` | admin-only |
| `scripts/make-cube-token.py` | выпуск per-role JWT (HS256 = `CUBEJS_API_SECRET`) |
| `.env` / `.env.example` | `CUBESQL_RBAC_USER/PASSWORD`, `CUBE_RBAC_USER_REGION` |
| `packages/harness/tests/test_rbac.py` | вся матрица «роль → доступ» (REST/SQL API/MCP/негативы) |

## Демо-сценарий «Admin vs User»

Стек: `just cube` (прод-режим — обязательно, см. ниже) + токены:

```bash
ADMIN_JWT=$(uv run python scripts/make-cube-token.py --group admin)
USER_JWT=$(uv run python scripts/make-cube-token.py --group user --region AFRICA)
```

### 1) REST /v1/meta — состав членов

```bash
curl -s -H "Authorization: $USER_JWT" localhost:4000/cubejs-api/v1/meta \
  | jq -c '.cubes[] | select(.name=="sales") | [.measures[].name]'
# user:   ["revenue","quantity","orders_count"]
# admin:  все 6 (вкл. avg_discount); fact_sales/sales_mov — только у admin
```

### 2) REST /v1/load — строки по регионам

```bash
curl -s -H "Authorization: $USER_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.customer_region"]}}' \
  localhost:4000/cubejs-api/v1/load | jq '.data'
# user:   1 строка — AFRICA
# admin:  5 строк; AFRICA-строка совпадает с user (сверка в test_rbac)
```

### 3) REST /v1/sql — фильтр вшит в компиляцию

```bash
curl -s -H "Authorization: $USER_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.market_segment"]}}' \
  localhost:4000/cubejs-api/v1/sql | jq -r '.sql.sql[0]' | grep WHERE
# WHERE ("dim_customer".customer_region = ?)  ← регион из подписанного claim
```

Обойти фильтр нельзя: он добавляется при компиляции, до исполнения (это же видно
в `artifacts/duckdb_query_log.csv` — тест `test_load_user_row_filter_in_query_log`).

### 4) SQL API :15432 (psql/DBeaver/psycopg) — per-role учётки

```bash
psql "host=localhost port=15432 user=$CUBESQL_RBAC_USER dbname=default" \
  -c 'SELECT sales.customer_region, SUM(sales.revenue) FROM sales GROUP BY 1'
# user:   ровно AFRICA
# admin (CUBESQL_USER): все 5 регионов
# SELECT AVG(sales.avg_discount) FROM sales → у admin число, у user — ошибка доступа
```

### 5) MCP-агент под ролью (обязательный сценарий)

Код MCP один на все роли — роль выбирается окружением запуска:

```bash
export $(grep -E 'CUBESQL_RBAC|CUBE_RBAC_USER_REGION' .env | xargs)
CUBEJS_API_TOKEN="$USER_JWT" \
CUBESQL_USER="$CUBESQL_RBAC_USER" CUBESQL_PASSWORD="$CUBESQL_RBAC_PASSWORD" \
  uv run python -m cube_mcp
# cube_meta → 3 меры; cube_load(revenue × customer_region) → 1 строка AFRICA;
# avg_discount агенту недоступен ни в meta, ни в запросах.
```

### 6) Evidence (admin-путь)

`just evidence` рендерит `connection.yaml` из `CUBESQL_USER` (группа admin) —
дашборды работают как раньше. Per-role дашборды = отрендерить второй connection
с `CUBESQL_RBAC_*` (Evidence 40.x не интерполирует env в connection.yaml).

## Токены и секреты

- `CUBEJS_API_SECRET` — ключ ПОДПИСИ JWT; сам по себе больше НЕ пароль:
  прод-режим принимает только подписанные JWT (сырой секрет → 403, тест
  `test_rest_raw_secret_rejected`).
- JWT: claims `groups` (+ `region` для user), короткий `exp`; группы попадают в
  запрос только через подпись — подделать нельзя.
- harness/MCP минтят admin-JWT автоматически (`harness/tokens.py`), поэтому
  `just verify` / `just bench` работают без ручных токенов.

## Подводные камни (найдены в бою)

1. **Dev mode отключает авторизацию** («Authentication checks are disabled in
   developer mode»): любой запрос становится admin, политики не применяются.
   Поэтому `just cube` запускает ПРОД-режим (`npm start`, `CUBEJS_DEV_MODE=false`
   в `packages/cube/.env`); playground — отдельный `just cube-dev`.
2. **`pgSqlPort`**: в dev mode SQL API :15432 включён по умолчанию, в проде —
   нет. Задан явно в `cube.js`.
3. **Cube Store**: прод-режим по умолчанию требует его для очереди/кэша —
   для локального DuckDB стоит `cacheAndQueueDriver: 'memory'`.
4. **Подлежащий куб под view**: RLS проходит по ВСЕМ кубам запроса, включая
   факт под витриной. Admin-only политика на `fact_sales` молча превращала
   любые запросы витрины под user в `WHERE 1=0`. Решение: политика `group: "*"`
   с пустым `includes` — прямые запросы deny, через витрину члены выдаются
   автоматически (view = security boundary, как в PostgreSQL).
5. **member_level в политике куба не принимает путей** (`dim_customer.customer_region`
   запрещён) — межкубовые row-фильтры описываются на view, где все члены в одном
   пространстве имён.
6. **Кэш нормализует запросы**: LIMIT и комментарии не меняют cache key — для
   гарантированного исполнения SQL в тестах ротируем семантику (год×месяц).
7. Политики разных групп для одного юзера **объединяются по членам (union)**,
   а строки — пересекаются по запрошенным членам (см. тест `test_meta_dual_group_union`).

## Чек-лист воспроизведения

```bash
just cube                                   # прод-режим, REST+SQL API+лог
uv run pytest packages/harness/tests/test_rbac.py -q   # вся матрица (18 тестов)
HARNESS_STRICT=1 uv run pytest packages/harness -q     # регресс verify-harness
uv run pytest -q                                       # всё, включая MCP e2e
```
