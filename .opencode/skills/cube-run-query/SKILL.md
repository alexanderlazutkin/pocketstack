---
name: cube-run-query
description: Выполнять запросы к семантическому слою Cube pocketstack через MCP-инструменты cube_load / sql_api (сервер cube, pocketstack-mcp) и интерпретировать результат. Use whenever someone wants numbers out of Cube — pull a metric, check a total, compare periods, verify a measure. Triggers on "how many", "show me revenue by month", "выручка по регионам", "сколько", "какой итог", "проверь метрику", "YoY", "MoM", "сравни периоды", "did that measure work". Модель сначала смотри через cube-explore-model; меняют модель через cube-build-model.
license: Apache-2.0
compatibility: MCP-сервер `cube` (pocketstack-mcp, packages/mcp) — инструменты cube_meta, cube_load, cube_sql, sql_api. Требует запущенный `just cube` (REST :4000, SQL API :15432). Cube Cloud/CLI не используется.
---

# Запрос к Cube (pocketstack)

## Инструменты (все read-only, MCP-сервер `cube`)

| Инструмент | Назначение |
| --- | --- |
| `cube_meta` | Каталог кубов/членов. **Начинай отсюда** — никогда не угадывай имена членов |
| `cube_load` | Выполнить семантический запрос (REST /v1/load, мимо кэша) |
| `cube_sql` | Показать SQL, который Cube сгенерирует (без исполнения) — ground truth |
| `sql_api` | Ad-hoc read-only SQL через pg-wire (:15432): таблица = имя куба, колонка = `куб.член` |

В opencode инструменты зовутся `cube_cube_meta`, `cube_cube_load`, `cube_cube_sql`, `cube_sql_api`.

## Петля запроса

1. **`cube_meta`** → найти членов по `title`/`description` («Выручка» → `sales.revenue`,
   «Регион клиента» → `sales.customer.region`). Формулу не сочинить — она в семантическом слое.
2. **`cube_load`**:

```
measures:   ["sales.revenue"]
dimensions: ["sales.customer.region"]
filters:    [{"member": "sales.calendar.year", "operator": "equals", "values": ["1997"]}]
limit:      50
```

   У нашего MCP нет `timeDimensions` — время фильтруй через `filters` по
   `sales.calendar.year/quarter/month/day` или `afterDate`/`beforeDate` на `order.order_date`.
3. сомневаешься в числе → **`cube_sql`** с теми же аргументами: видно точный SQL,
   который уйдёт в DuckDB.

## Правила pocketstack

- **YoY/PoP считает куб `sales_mov`, а не агент.** Готовые члены: `sales_mov.abs_yoy_sum`,
  `sales_mov.rel_yoy_avg`, размерности `sales_mov.ym/year/month`. Не вычисляй отклонения
  в голове и не джойни два запроса руками.
- Основная точка входа — view `sales` (факт + разрезы с префиксами:
  `customer.*`, `part.*`, `supplier.*`, `order.*`, `calendar.*`). Кубы `fact_sales`, dims —
  внутренние.
- Сырой SQL (`sql_api`) — для проверки паритета и диагностики, не для бизнес-метрик:
  метрика, посчитанная в обход семантического слоя, не защищена моделью.

## Интерпретация результата

- Назови число, затем как оно получено: мера, диапазон, фильтры. Число без запроса — не проверяемо.
- Пустой `data: []` — это результат, а не ошибка. Не подменяй запрос молча.
- Не выдумывай значения. Ошибка запроса → сообщи её как есть.
- Сверка с harness: `just verify` (запущенный `just cube` обязателен).

## Если сломалось

| Симптом | Причина |
| --- | --- |
| MCP-инструменты недоступны | Не запущен `just cube` или MCP-сервер: проверь `just cube` (REST :4000) |
| `Member not found` | Имя не то или член не включён во view — перечитай `cube_meta`, не перебирай варианты |
| `{"error":"Continue wait"}` | DuckDB ещё считает — повтори тот же запрос |
| Connection refused :15432 | SQL API не поднялся — смотри логи `just cube` |
