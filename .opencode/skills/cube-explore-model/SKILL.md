---
name: cube-explore-model
description: Исследовать семантическую модель Cube pocketstack — кубы, view, меры, измерения, join-ы — через MCP-инструмент cube_meta и YAML-файлы модели. Use before any query or model change: find the right member, understand a metric formula, assess impact of a change. Triggers on "какие метрики есть", "где описана revenue", "что за куб sales_mov", "what members exist", "find the measure for", "impact of renaming", "покажи модель". Запросы — cube-run-query; изменения — cube-build-model.
license: Apache-2.0
compatibility: MCP-сервер `cube` (pocketstack-mcp, packages/mcp) — cube_meta; файлы модели packages/cube/model/. Cube Cloud/CLI не используется.
---

# Исследование модели (pocketstack)

## Два источника, всегда оба

| Источник | Что даёт |
| --- | --- |
| MCP `cube_meta` | Скомпилированная модель: кубы, члены, `title`/`description` (рус.), типы. Это то, что реально queryable |
| Файлы `packages/cube/model/` | Исходники: `cubes/*.cube.yml`, `views/sales.view.yml`. Формулы SQL, joins, pre-aggregations |

`cube_meta` отвечает, ЧЕМ можно запросить; YAML — ПОЧЕМУ оно так считается.
Измерение может существовать в кубе, но не быть включённым во view `sales` — тогда оно
не queryable. Разницу видно только в мете против YAML.

## Карта модели

- **view `sales`** — точка входа всех бизнес-запросов: `fact_sales` (весь `includes: "*"`)
  + разрезы с префиксами алиасов: `customer.region`, `part.brand`, `supplier.nation`,
  `order.status`, `order.order_date`, `calendar.year/quarter/month/day`.
- **куб `sales_mov`** — готовые отклонения YoY/PoP: `revenue`, `revenue_ly`, `abs_yoy`,
  `rel_yoy`, меры `abs_yoy_sum`, `rel_yoy_avg`, размерность `ym` (= year*100+month).
- **кубы `fact_sales`, `dim_*`** — физический слой; наружу только через view.
- Семантика метрик (формула, единицы, ограничения) живёт в `description` членов —
  это канал доставки смысла агенту (см. `docs/cube-mcp.md`).

## Порядок работы

1. `cube_meta` → найти кандидата по title/description.
2. Открыть YAML файла куба → прочитать `sql` меры, joins,granularity.
3. Для вопроса «как получится SQL» — `cube_sql` с этими членами (без исполнения).

## Impact-анализ перед изменением

Веток dev-mode нет (OSS) —impact считается по коду:

- поиск имени члена по `packages/cube/model/` (переименование ломает view includes);
- поиск по `packages/harness/` — golden-вопросы и паритет SQL опираются на имена членов;
- поиск по `packages/evidence/` — дашборды Evidence используют те же члены.

Переименование члена = правка во всех трёх местах разом, иначе `just verify` упадёт.

## Если сломалось

| Симптом | Причина |
| --- | --- |
| Члена нет в мете | Не включён во view / опечатка / cube dev не перечитал файл — перезапусти `just cube` |
| Мета расходится с YAML | `just cube` держит старую сборку — файлы читает hot-reload, сомневаешься → перезапуск |
