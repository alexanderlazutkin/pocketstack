# RBAC в Cube OSS: access_policy + группы из JWT (Admin vs User)

> Per-role доступ к семантическому слою pocketstack на чистом Cube OSS
> (framework access policies, PR cube-js/cube.js#8766 — в OSS с конца 2024).
> Enterprise отличается только UI/CLI-управлением ролями — сам механизм в OSS.
> Роли: **admin видит всё; user — ровно 3 меры и только свой регион**.

**Стек по умолчанию работает под ролью admin.** Ничего дополнительного делать не
нужно: учётка SQL API `CUBESQL_USER` = admin, harness/MCP сами подписывают
admin-JWT (`harness/tokens.py`), Evidence рендерится с admin-кредами. Роль user
появляется только там, где вы явно берёте user-токен/учётку (Часть B/C ниже).

## Режимы сервера: dev (по умолчанию) vs прод — как включать/выключать

Переключатель — `CUBEJS_DEV_MODE` в `packages/cube/.env` (**по умолчанию `true`**);
npm-скрипты `packages/cube` переопределяют его без правки файла. После смены —
перезапуск (`scripts/stack.sh restart`).

| Режим | Как запустить | Что даёт |
| --- | --- | --- |
| **dev** (по умолчанию) | `just cube` (= `just cube-dev`, `CUBEJS_DEV_MODE=true`) | **Playground UI** на http://localhost:4000, hot-reload модели, SQL API `:15432`. Токены не проверяются; запрос **без токена = admin** (dev-фолбэк в `contextToGroups`), с токеном `access_policy` применяется как в проде |
| **прод** | `just cube-prod` (`npm run prod`, `CUBEJS_DEV_MODE=false`) | строгие проверки: подписанные JWT / учётки SQL API, сырой секрет → 403; весь RBAC из этого документа |

**Важно:** dev отключает только проверку токенов — `access_policy` компилируется
в SQL и в dev. Поэтому безтокенный запрос (Playground) без dev-фолбэчка в
`contextToGroups` (`cube.js`) получал бы deny by default (`WHERE 1=0`); фолбэк
назначает ему группу admin. Полный RBAC-прогон (`just verify` → `test_rbac.py`)
работает **только в прод-режиме** `just cube-prod`; в dev RBAC-тесты
автоматически пропускаются (dev-поведение покрыто `test_dev_mode.py`).

```bash
just cube          # dev (по умолчанию): playground :4000, RBAC off
just cube-prod     # прод: RBAC on — сценарии B/C и just verify
# вручную: CUBEJS_DEV_MODE=true|false в packages/cube/.env + scripts/stack.sh restart
```

## Модель доступа

```
┌─────────────────────── Кто ───────────────────────┐
│ REST :4000      JWT (just token / scripts/…)      │
│                 claims: { groups, region }        │
│ SQL API :15432  учётка (checkSqlAuth в cube.js)   │
│                 pocketstack=admin | …_user=user    │
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

| Группа | Меры витрины `sales` | Строки | Прямые кубы `fact_sales`/`sales_mov` |
| --- | --- | --- | --- |
| `admin` (по умолчанию) | все 6 (вкл. `avg_discount`) | все регионы | ✅ |
| `user` | **ровно 3**: `revenue`, `quantity`, `orders_count` | только свой регион | ❌ deny |
| без группы / прочие | — | — | ❌ **deny by default** |

Справочники `dim_*` без политик (reference data) — доступны обеим ролям.

## Где что живёт

| Файл | Роль |
| --- | --- |
| `packages/cube/cube.js` | `contextToGroups` (группы из подписанных claims), `checkSqlAuth` (per-role учётки SQL API), `pgSqlPort`, `cacheAndQueueDriver: 'memory'` |
| `packages/cube/model/views/sales.view.yml` | `access_policy` витрины: admin всё; user 3 меры + `row_level` по `customer_region` |
| `packages/cube/model/cubes/fact_sales.cube.yml` | факт только через витрину (см. «Подводные камни»); admin — всё |
| `packages/cube/model/cubes/sales_mov.cube.yml` | admin-only |
| `scripts/make-cube-token.py`, `just token` | выпуск per-role JWT (HS256 = `CUBEJS_API_SECRET`) |
| `.env` / `.env.example` | `CUBESQL_RBAC_USER/PASSWORD`, `CUBE_RBAC_USER_REGION` |
| `packages/harness/tests/test_rbac.py` | вся матрица «роль → доступ» (19 тестов) |

---

## Руководство по проверке пользователем (пошагово)

Каждый шаг = цель → команда → ожидаемый результат. Копируйте команды целиком
(блоки самодостаточны). Числа в примерах — от текущего sf; при другом объёме
данных суммы изменятся, но соотношения (5 регионов у admin / 1 у user,
совпадение цифр между шагами) — нет.

### Шаг 0. Предусловия (один раз)

```bash
# 0.1. .env заполнен, включая RBAC-переменные (шаблон .env.example):
#      CUBEJS_API_SECRET, CUBESQL_USER/PASSWORD (admin),
#      CUBESQL_RBAC_USER/PASSWORD (user), CUBE_RBAC_USER_REGION (напр. AFRICA)
grep -E 'CUBESQL_RBAC_USER|CUBE_RBAC_USER_REGION' .env

# 0.2. Стек поднят в ПРОД-режиме (авторизация ВКЛЮЧЕНА; это роль admin):
just cube-prod     # или CUBEJS_DEV_MODE=false + scripts/stack.sh up; REST :4000 + SQL API :15432

# 0.3. Стек жив и по умолчанию admin — 200 и полный список кубов:
ADMIN_JWT=$(just token 2>/dev/null)
curl -s -H "Authorization: $ADMIN_JWT" localhost:4000/cubejs-api/v1/meta | jq -c '[.cubes[].name]'
# ожидание: ["dim_customer","dim_date","dim_order","dim_part","dim_supplier",
#            "fact_sales","sales_mov","sales"]
```

Нужны `curl`, `jq`, `psql` (для SQL API), `uv`. Пароли берутся из `.env`
переменными `PGPASSWORD` — в команды не вбиваются руками.

### Часть A. Admin — роль стека по умолчанию

Выполняется без каких-либо переключений ролей: это «как работало всегда».

**A1. REST /v1/meta — видны ВСЕ 6 мер витрины sales:**

```bash
ADMIN_JWT=$(just token 2>/dev/null)
curl -s -H "Authorization: $ADMIN_JWT" localhost:4000/cubejs-api/v1/meta \
  | jq -c '[.cubes[] | select(.name=="sales") | .measures[].name]'
```

Ожидание — 6 мер, включая `avg_discount`:

```text
["sales.revenue","sales.revenue_with_tax","sales.quantity","sales.lines_count","sales.orders_count","sales.avg_discount"]
```

**A2. REST /v1/load — данные ВСЕХ 5 регионов:**

```bash
curl -s -H "Authorization: $ADMIN_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.customer_region"]}}' \
  localhost:4000/cubejs-api/v1/load | jq -c '[.data[] | .["sales.customer_region"]]'
```

Ожидание: `["EUROPE","ASIA","AMERICA","AFRICA","MIDDLE EAST"]` — 5 регионов.
Запомните/сохраните AFRICA-строку целиком — она понадобится в B2:

```bash
curl -s -H "Authorization: $ADMIN_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.customer_region"]}}' \
  localhost:4000/cubejs-api/v1/load | jq -c '.data[] | select(.["sales.customer_region"]=="AFRICA")'
# пример: {"sales.customer_region":"AFRICA","sales.revenue":"43488870851.6861"}
```

**A3. REST /v1/sql — компиляция БЕЗ принудительного фильтра (allow_all):**

```bash
curl -s -H "Authorization: $ADMIN_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.market_segment"]}}' \
  localhost:4000/cubejs-api/v1/sql | jq -r '.sql.sql[0]' | tail -1
```

Ожидание: в SQL нет строк `WHERE ... customer_region` (фильтр не вшит).

**A4. SQL API :15432 под учёткой admin (CUBESQL_USER) — полный доступ:**

```bash
export $(grep -E '^CUBESQL_(USER|PASSWORD)=' .env | xargs)
PGPASSWORD="$CUBESQL_PASSWORD" psql "host=localhost port=15432 user=$CUBESQL_USER dbname=default" \
  -tAc 'SELECT sales.customer_region, SUM(sales.revenue) FROM sales GROUP BY 1 ORDER BY 1'
```

Ожидание — 5 строк:

```text
AFRICA|43488870851.6861
AMERICA|43565312628.9458
ASIA|43858010644.9379
EUROPE|44032702326.2956
MIDDLE EAST|43157327433.1347
```

И мера `avg_discount` доступна (контраст для B6):

```bash
PGPASSWORD="$CUBESQL_PASSWORD" psql "host=localhost port=15432 user=$CUBESQL_USER dbname=default" \
  -tAc 'SELECT ROUND(AVG(sales.avg_discount),4) FROM sales'
# ожидание: 0.05
```

### Часть B. User — роль включается явно

**B0. Подготовка (в каждом новом шелле):**

```bash
USER_JWT=$(just token user AFRICA 2>/dev/null)   # регион = CUBE_RBAC_USER_REGION
export $(grep -E '^CUBESQL_RBAC_(USER|PASSWORD)=' .env | xargs)
```

**B1. REST /v1/meta — РОВНО 3 меры, факт-кубы исчезли:**

```bash
curl -s -H "Authorization: $USER_JWT" localhost:4000/cubejs-api/v1/meta \
  | jq -c '[.cubes[] | select(.name=="sales") | .measures[].name]'
curl -s -H "Authorization: $USER_JWT" localhost:4000/cubejs-api/v1/meta | jq -c '[.cubes[].name]'
```

Ожидание:

```text
["sales.revenue","sales.quantity","sales.orders_count"]          # 3 меры, avg_discount нет
["dim_customer","dim_date","dim_order","dim_part","dim_supplier","sales"]  # fact_sales/sales_mov исчезли
```

**B2. REST /v1/load — ТОЛЬКО свой регион, числа = admin (шаг A2):**

```bash
curl -s -H "Authorization: $USER_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.customer_region"]}}' \
  localhost:4000/cubejs-api/v1/load | jq -c '[.data[] | {(.["sales.customer_region"]): .["sales.revenue"]}]'
```

Ожидание — ровно 1 строка, и выручка ПОБАЙТОВО равна AFRICA-строке из A2:

```text
[{"AFRICA":"43488870851.6861"}]
```

**B3. REST /v1/load — запрещённая мера → отказ:**

```bash
curl -s -H "Authorization: $USER_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.avg_discount"],"dimensions":["sales.customer_region"]}}' \
  localhost:4000/cubejs-api/v1/load | jq -r '.error' | head -c 120; echo
```

Ожидание: `Error: You requested hidden member: 'sales.avg_discount'...`

**B4. REST /v1/sql — row_level-фильтр ВШИТ в компиляцию:**

```bash
curl -s -H "Authorization: $USER_JWT" -H 'Content-Type: application/json' \
  -d '{"query":{"measures":["sales.revenue"],"dimensions":["sales.market_segment"]}}' \
  localhost:4000/cubejs-api/v1/sql | jq -c '.sql.sql'
```

Ожидание: в SQL есть `WHERE ("dim_customer".customer_region = ?)`, а в
параметрах — `["AFRICA"]`. Регион в запросе НЕ запрашивался — фильтр добавил
семантический слой, обойти его из клиента невозможно.

**B5. SQL API :15432 под учёткой user — только свой регион:**

```bash
PGPASSWORD="$CUBESQL_RBAC_PASSWORD" psql "host=localhost port=15432 user=$CUBESQL_RBAC_USER dbname=default" \
  -tAc 'SELECT sales.customer_region, SUM(sales.revenue) FROM sales GROUP BY 1'
```

Ожидание — 1 строка, равная AFRICA-строкам из A2/A4/B2:

```text
AFRICA|43488870851.6861
```

**B6. SQL API — запрещённая мера → ошибка планирования (у admin в A4 работало):**

```bash
PGPASSWORD="$CUBESQL_RBAC_PASSWORD" psql "host=localhost port=15432 user=$CUBESQL_RBAC_USER dbname=default" \
  -tAc 'SELECT AVG(sales.avg_discount) FROM sales'
```

Ожидание: `ERROR: ... No field named 'sales.avg_discount'. Valid fields are
'sales.revenue', 'sales.quantity', 'sales.orders_count', ...` — поля для user
просто не существуют.

**B7. SQL API — неверный пароль → отказ подключения:**

```bash
PGPASSWORD="definitely-wrong" psql "host=localhost port=15432 user=$CUBESQL_RBAC_USER dbname=default" -tAc 'SELECT 1'
```

Ожидание: `FATAL: password authentication failed for user "pocketstack_user"`.

**B8. REST — запрос без токена и с сырым секретом → 403:**

```bash
curl -s -o /dev/null -w "без токена: %{http_code}\n" localhost:4000/cubejs-api/v1/meta
RAW=$(grep CUBEJS_API_SECRET .env | cut -d= -f2)
curl -s -o /dev/null -w "сырой секрет: %{http_code}\n" -H "Authorization: $RAW" localhost:4000/cubejs-api/v1/meta
```

Ожидание: обе строки `403`. Прод-режим принимает только подписанные JWT —
сам секрет больше не пароль.

**B9. REST — подписанный токен БЕЗ групп → deny by default:**

```bash
NOGROUP=$(uv run python -c "from harness.env import load_env, required; from harness.tokens import mint_cube_token; load_env(); print(mint_cube_token(required('CUBEJS_API_SECRET'), {}, 300))" 2>/dev/null)
curl -s -H "Authorization: $NOGROUP" localhost:4000/cubejs-api/v1/meta \
  | jq -c '[.cubes[] | select(.name=="sales") | .measures[].name]'
```

Ожидание: `[]` — токен валиден, но группа не объявлена → мер нет.

### Часть C. MCP-агент (обязательный инструмент демо)

Код MCP один на все роли: роль задаётся только окружением запуска.

**C1. Агент под ролью user — 3 меры, 1 регион, запрет avg_discount:**

```bash
export $(grep -E '^CUBESQL_RBAC_(USER|PASSWORD)=' .env | xargs)
export CUBEJS_API_TOKEN="$(just token user AFRICA 2>/dev/null)"
CUBESQL_USER="$CUBESQL_RBAC_USER" CUBESQL_PASSWORD="$CUBESQL_RBAC_PASSWORD" \
uv run python - <<'EOF' 2>/dev/null
import json
from cube_mcp import client
sales = next(c for c in json.loads(client.cube_meta())["cubes"] if c["name"] == "sales")
print("меры:", sorted(m["name"] for m in sales["measures"]))
print("load:", json.loads(client.cube_load(["sales.revenue"], ["sales.customer_region"]))["rows"])
try:
    client.cube_load(["sales.avg_discount"], ["sales.customer_region"])
    print("avg_discount: РАЗРЕШЁН (нарушение!)")
except RuntimeError:
    print("avg_discount: отказ (корректно)")
EOF
```

Ожидание:

```text
меры: ['sales.orders_count', 'sales.quantity', 'sales.revenue']
load: [{'sales.customer_region': 'AFRICA', 'sales.revenue': '43488870851.6861'}]
avg_discount: отказ (корректно)
```

То же самое — подключение агента (opencode/Claude Code) с env роли:

```bash
export $(grep -E '^CUBESQL_RBAC|CUBE_RBAC_USER_REGION' .env | xargs)
CUBEJS_API_TOKEN="$(just token user AFRICA 2>/dev/null)" \
CUBESQL_USER="$CUBESQL_RBAC_USER" CUBESQL_PASSWORD="$CUBESQL_RBAC_PASSWORD" \
  uv run python -m cube_mcp
```

**C2. Агент по умолчанию — admin (ничего не экспортировали):**

```bash
unset CUBEJS_API_TOKEN CUBESQL_RBAC_USER CUBESQL_RBAC_PASSWORD 2>/dev/null
uv run python -c "
import json; from cube_mcp import client
sales = next(c for c in json.loads(client.cube_meta())['cubes'] if c['name']=='sales')
print('меры:', len(sales['measures']))" 2>/dev/null
```

Ожидание: `меры: 6` — MCP сам подписал admin-JWT на `CUBEJS_API_SECRET`.

### Часть D. Evidence (дашборды) — admin по умолчанию

```bash
just evidence    # localhost:3000; connection.yaml рендерится из CUBESQL_USER (admin)
```

Ожидание: дашборды работают как раньше — «Регионы» показывает все 5 регионов.
Per-role дашборды = отрендерить второй `connection.yaml` с `CUBESQL_RBAC_*`
(Evidence 40.x не интерполирует env в connection.yaml).

### Часть E. Автотесты (вся матрица одним прогоном)

```bash
uv run pytest packages/harness/tests/test_rbac.py -q   # 19 тестов: части A/B/C + негативы
HARNESS_STRICT=1 uv run pytest packages/harness -q     # регресс verify-harness (88)
uv run pytest -q                                       # всё, включая MCP e2e (136)
```

Ожидание: `19 passed`, `88 passed`, `136 passed` (числа — на момент гайда).

### Сводная таблица «что должно получиться»

| Проверка | admin (по умолчанию) | user |
| --- | --- | --- |
| Меры в `/meta` (A1/B1) | 6, вкл. `avg_discount` | ровно 3: revenue, quantity, orders_count |
| Кубы в `/meta` (A1/B1) | вкл. `fact_sales`, `sales_mov` | только `sales` + справочники |
| Регионы в `/load` (A2/B2) | 5 | 1 (свой); выручка = строке admin |
| `avg_discount` (A4/B3/B6) | считается | отказ (REST и SQL API) |
| `/v1/sql` (A3/B4) | без фильтра | `WHERE customer_region = ?` c `[AFRICA]` |
| SQL API регионы (A4/B5) | 5 строк | 1 строка, число = admin |
| Пароль/токен (B7/B8/B9) | — | неверный → FATAL; без токена/сырой секрет → 403; без групп → 0 мер |
| MCP (C1/C2) | 6 мер | 3 меры, 1 регион, avg_discount — отказ |

---

## Токены и секреты

- `CUBEJS_API_SECRET` — ключ ПОДПИСИ JWT; сам по себе НЕ пароль (прод-режим:
  сырой секрет → 403, тест `test_rest_raw_secret_rejected`).
- JWT: claims `groups` (+ `region` для user), короткий `exp` (`just token ...`
  печатает токен в stdout, описание claims — в stderr). Группы попадают в
  запрос только через подпись — подделать нельзя.
- harness/MCP минтят admin-JWT автоматически — `just verify`/`just bench`
  работают без ручных токенов.

## Подводные камни (найдены в бою)

1. **Dev mode отключает проверку токенов, но НЕ access_policy**: Playground
   ходит без токена → групп нет → deny by default (`WHERE 1=0`). Поэтому в
   `contextToGroups` есть dev-фолбэк: безтокенный запрос = admin. По умолчанию
   стек в dev (`packages/cube/.env`: `CUBEJS_DEV_MODE=true`, `just cube` —
   playground); строгий RBAC — прод: `just cube-prod` (`npm run prod`).
   См. «Режимы сервера» в начале документа и docs/gotchas.md.
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
   а строки — пересекаются по запрошенным членам (тест `test_meta_dual_group_union`).
8. **env роли живёт в рамках одного запуска**: `CUBEJS_API_TOKEN`/`CUBESQL_*`
   нужно экспортировать в ТОМ ЖЕ шелле/команде, где стартует MCP-агент —
   пустая переменная молча откатывает на admin (см. C1/C2).
