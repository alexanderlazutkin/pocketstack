# MCP-сервер pocketstack/cube

Тонкий MCP-сервер (stdio) вокруг семантического слоя Cube — Stage 5 плана.

**Почему свой**: официального MCP-пакета у Cube нет (`@cubejs-backend/mcp` — 404,
галлюцинированное имя); `/mcp` — endpoint Enterprise/Cube Cloud, к локальному
OSS-Cube неприменим (проверено: `localhost:4000/mcp` → 404). Поэтому — обёртка
над существующими API, теми же путями, что проверяет harness.

## Семантика на языке запросов AI-агента

Описания в моделях — не документация «для людей в сторонке», а **канал доставки бизнес-смысла
агенту**. Контур:

```
*.cube.yml (description/title, рус.)
   → GET /cubejs-api/v1/meta (поля description, title у каждого члена)
     → MCP-инструмент cube_meta (as-is)
       → контекст агента → формулировка запроса cube_load
```

Агент отвечает на вопрос пользователя («выручка по регионам в 1997») так:
1. `cube_meta` → находит членов не по имени, а по `title`/`description`: «Выручка» → `sales.revenue`,
   «Регион клиента» → `sales.customer.region`.
2. Читает `description` метрики → узнаёт формулу (после скидки, до налога), единицу, ограничения.
3. Формирует `cube_load`. Формулу агент **не сочиняет** — она уже описана в семантическом слое.

Поэтому описания пишутся на русском (язык вопросов), имена членов остаются английскими.

### Правила описаний

| Правило | Пример |
|---|---|
| Бизнес-термин + синонимы вопроса | «Главная метрика выручки (revenue)» |
| Единица измерения всегда | «ден. ед.», «шт», «дней», «%», «п.п.» |
| Перечисление допустимых значений | «R — возвращена, A — принята, N — без статуса» |
| Формула производного поля | «extended_price × (1 − discount) × (1 + tax)» |
| Grain и ловушки агрегации | «атрибут заказа: SUM по позициям даст завышение» |
| Не дублировать SQL и реализацию | про DuckDB/sqlmesh — молчим |

Описание куба отвечает «что это за сущность и grain», описание члена — «что значит и как
интерпретировать число». `title` — короткое русское имя для сопоставления с вопросом.

Все модели слоя витрин (marts) описаны: `fact_sales`, `dim_customer`, `dim_order`, `dim_part`,
`dim_supplier`, `dim_date`, `sales_mov`, view `sales`. Основа терминологии — спецификация
TPC-H v3.0.1 §1.1–1.4 (бизнес-контекст оптового поставщика) + формулы производных полей
из sqlmesh-моделей. В view описания членов наследуются из кубов (с префиксом алиаса:
`customer.region` и т.п.).

Проверить, что описание доехало до агента:

```bash
# /meta напрямую (токен из .env, см. harness)
curl -s localhost:4000/cubejs-api/v1/meta -H "Authorization: $TOKEN" \
  | jq '.cubes[] | select(.name=="sales_mov") | .measures[] | {name, title, description}'
# или через MCP: cube_meta() и искать description у нужного члена
```

## Сценарии проверки MCP через AI-агента

Демо-прогон AI-агента (opencode/Claude Code с подключённым MCP `cube`) по живому стеку.
Каждый сценарий: вопрос агенту **на русском** (как его задаёт пользователь) → шаги (какие
tools должен вызвать) → ожидаемые числа (TPC-H sf=1, проверены по reference-SQL и живому
Cube 2026-10-26) → критерий успеха. Cube отдаёт числа с большим числом знаков — сравнение
«до копейки» = совпадение после округления до 0.01.

Предусловия: куб поднят (`just serve-up`), `.env` на месте, MCP подключён.

### С1. Метрика через MCP = дашборд (числовой паритет)

**Вопрос агенту:** «Какая выручка по регионам клиентов в 1997 году?»

| Шаг | Tool | Действие |
|---|---|---|
| 1 | `cube_meta` | найти меру «Выручка» → `sales.revenue`, разрез «Регион клиента» → `sales.customer_region` |
| 2 | `cube_load` | `measures=["sales.revenue"]`, `dimensions=["sales.customer_region"]`, `filters=[sales.year equals 1997]` |
| 3 | — | сверка с Evidence `localhost:3000/verification#revenue_by_region` (год 1997) |

**Ожидание (5 строк, сумма = 33 116 752 392.08):**

| Регион | Выручка |
|---|---|
| AFRICA | 6 617 193 598.97 |
| AMERICA | 6 644 117 360.27 |
| ASIA | 6 639 613 487.61 |
| EUROPE | 6 626 811 347.14 |
| MIDDLE EAST | 6 589 016 598.08 |

**Успех:** числа совпали до копейки; агент сам выбрал членов по `title`/`description`
из `cube_meta`, не писал SQL руками.

### С2. Объясни семантику, не придумывая (формулы из слоя)

**Вопрос агенту:** «На сколько процентов выручка января 1997 отличается от декабря 1996
и от января 1996? Объясни, как это считается».

| Шаг | Tool | Действие |
|---|---|---|
| 1 | `cube_meta` | куб `sales_mov` — мерки/разрезы отклонений |
| 2 | `cube_sql` | SQL для `sales_mov.revenue` × [revenue_pop, rel_pop, revenue_ly, rel_yoy] за январь 1997 — **читает формулу из сгенерированного SQL** |
| 3 | `cube_load` | те же члены, фильтры `year=1997, month=1` |

**Ожидание (январь 1997):** выручка 2 819 023 795.53; PoP против декабря 1996
(2 839 599 697.49) = **−0.7246%**; YoY против января 1996 (2 803 469 770.78) = **+0.5548%**.

**Успех:** объяснение агента опирается на увиденный в `cube_sql` непрерывный индекс
`ym = year*12 + month` (`prev.ym = cur.ym − 1`, `ly.ym = cur.ym − 12`), а не на выдуманную
формулу. Ловушка: наивный `month − 1` для января даёт «нет предыдущего месяца» — агент
должен показать, что предыдущий месяц = декабрь 1996.

### С3. Мини-harness в чате (тройное равенство)

**Вопрос агенту:** «Проверь выручку 1997 года по кварталам тремя независимыми способами».

| Шаг | Tool | Источник |
|---|---|---|
| 1 | `cube_load` | `sales.revenue × sales.quarter`, фильтр `sales.year=1997` |
| 2 | `sql_api` | `SELECT sales.quarter, SUM(sales.revenue) FROM sales WHERE sales.year = 1997 GROUP BY 1 ORDER BY 1` |
| 3 | — | страница Evidence `#revenue_1997_by_quarter` (ground truth harness) |

**Ожидание (кварталы 1–4):** 8 195 274 134.38 / 8 247 068 945.42 / 8 367 977 616.53 /
8 306 431 695.75 (сумма 33 116 752 392.08).

**Успех:** три числа равны до копейки; агент проговаривает, что повторил схему harness:
REST ↔ SQL API ↔ reference.

### С4. Семантическая навигация и ловушки (проверка русских описаний)

Вопросы без имён членов — агент должен сопоставить бизнес-слова с описаниями из `cube_meta`.

**Вопрос 4а:** «Сколько денег принесли клиенты из Европы в сегменте машин в 1996?»

- «деньги принесли» → `sales.revenue` (description: «главная метрика выручки»);
  «клиенты из Европы» → `sales.customer_region = 'EUROPE'` (**не** `supplier_region`);
  «сегмент машин» → `sales.market_segment = 'AUTOMOBILE'` (значения перечислены в description).
- `cube_load`: фильтры region+segment+year=1996, мера `sales.revenue`.
- **Ожидание:** 1 339 179 718.89.

**Вопрос 4б (ловушка агрегации):** «Какова общая сумма всех заказов?»

- Правильный путь: `sql_api` → `SELECT SUM(dim_order.total_price) FROM dim_order` →
  **226 829 306 447.46** (заголовки заказов; самого члена нет в витрине `sales` — и это
  подсказано description'ом «атрибут заказа, SUM по позициям даст завышение»).
- **Провал:** SUM по факт-таблице (6 млн позиций) → завышение в разы.

**Успех:** члены выбраны по `description`; регион клиента не перепутан с регионом
поставщика; ловушка `total_price` распознана и объяснена словами из семантического слоя.

### Чек-лист оценки ответа агента (все сценарии)

1. Числа совпали с эталоном до копейки (0.01).
2. Агент не писал SQL руками, когда есть готовый член (`sales`, `sales_mov`).
3. Формулы и термины взяты из `description`/`cube_sql`, не выдуманы.
4. Указаны единицы (ден. ед., %, шт, п.п.).
5. Ответ на русском; имена членов в вызовах — английские.



## Инструменты (все read-only)

| Tool | Куб | Что делает |
|---|---|---|
| `cube_meta` | `GET /cubejs-api/v1/meta` | кубы/меры/измерения — с этого начинать |
| `cube_load` | `POST /v1/load` + `renewQuery: true` | выполнить запрос **мимо кэша**; ответ: rows, row_count, duration_ms |
| `cube_sql` | `POST /v1/sql` | показать SQL, который Cube сгенерирует (без исполнения) — ground-truth стиль |
| `sql_api` | pg-wire `:15432` | произвольный read-only SQL (только SELECT/WITH/SHOW/DESCRIBE/EXPLAIN, лимит 200 строк) |

Креды — из `.env` (`CUBEJS_API_SECRET`, `CUBESQL_USER`, `CUBESQL_PASSWORD` через
`harness.env`); сервер сам их загружает — в конфиге клиента секретов нет.

### Агент под ролью RBAC (docs/cube-rbac.md)

Код MCP не зависит от роли — она задаётся окружением запуска: REST-токен через
`CUBEJS_API_TOKEN` (готовый JWT любой группы), креды SQL API — обычными
`CUBESQL_*`. Агент с user-токеном видит 3 меры и только свой регион:

```bash
export $(grep -E 'CUBESQL_RBAC|CUBE_RBAC_USER_REGION' .env | xargs)
CUBEJS_API_TOKEN="$(uv run python scripts/make-cube-token.py --group user --region AFRICA)" \
CUBESQL_USER="$CUBESQL_RBAC_USER" CUBESQL_PASSWORD="$CUBESQL_RBAC_PASSWORD" \
  uv run python -m cube_mcp
```

Матрица «роль → доступ» для MCP покрыта тестом `test_rbac.py::test_mcp_user_role`.

## Подключение

### opencode

```bash
opencode mcp add cube -- uv run --directory /полный/путь/к/pocketstack python -m cube_mcp
```

(или в `opencode.json`: `{"mcp": {"cube": {"type": "local", "command": "uv",
"args": ["run", "--directory", "/путь/к/pocketstack", "python", "-m", "cube_mcp"]}}}`)

### Claude Code

```bash
claude mcp add cube -- uv run --directory /полный/путь/к/pocketstack python -m cube_mcp
```

### Ручная проверка (MCP Inspector)

```bash
npx @modelcontextprotocol/inspector uv run --directory /путь/к/pocketstack python -m cube_mcp
```

## Тесты

```bash
uv run pytest packages/mcp -q        # 9 тестов: unit + e2e (stdio-клиент SDK)
```

E2e-тест спавнит сервер как это делает реальный клиент (stdio) и проверяет
list_tools + call_tool. Требует живого куба (`just serve-up`) и `.env`.

## Пример сессии агента

1. `cube_meta()` → видит кубы `sales`, `sales_mov` и их членов.
2. `cube_load(measures=["sales_mov.revenue"], dimensions=["sales_mov.month"], filters=[{"member": "sales_mov.year", "operator": "equals", "values": ["1997"]}])` → 12 строк.
3. `cube_sql(...)` → показывает SQL с CTE/self-join — агент объясняет семантику YoY/PoP, не придумывая формулы.

Отклонения/метрики считаются в **Cube** — агент только вызывает готовых членов
(instructions сервера это прямо требуют).
