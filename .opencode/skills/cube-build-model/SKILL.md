---
name: cube-build-model
description: Создавать и менять семантическую модель Cube pocketstack — кубы, view, меры, измерения, joins, pre-aggregations в YAML-файлах packages/cube/model/ — с проверкой через MCP (cube_meta/cube_load/cube_sql) и harness. Use whenever someone wants to add a metric, define a measure, create a cube or view, join cubes, fix a model error, rename a field. Triggers on "add a metric", "добавь метрику", "создай view", "expose this field", "join orders to customers", "fix the model", "почини модель", "добавь pre-aggregation". Сначала читай модель через cube-explore-model; число проверяй через cube-run-query.
license: Apache-2.0
compatibility: Проект pocketstack (OSS Cube): правка YAML в packages/cube/model/, dev-сервер `just cube`, MCP-сервер `cube` (pocketstack-mcp) для проверок. Cube Cloud/CLI и dev-branch workflow не используются.
---

# Сборка/правка модели (pocketstack)

Пишет состояние. Ветки dev-mode Cube Cloud недоступны (OSS): **git-ветка проекта
и есть dev-ветка модели**, публикация = commit.

## Петля изменения

1. **Прочитай перед правкой.** `cube_meta` (MCP) + YAML соседних кубов — не сочиняй
   модель по предположению. Повторяй конвенции файла: layout, нейминг, где живут меры.
2. **Правь YAML** в `packages/cube/model/cubes/` (один куб — один файл,
   имя файла = имя куба) или `views/sales.view.yml` (включение членов в витрину).
   Новая бизнес-метрика обычно: мера в кубе → expose во view `sales`.
3. **Валидация компиляции:** `just cube` hot-reload-ит файлы. Проверь:
   - `cube_meta` — новый член появился в скомпилированной модели;
   - упало — ошибка компиляции Cube в логах `just cube` назовёт файл и члена,
     передавай её дословно, не гадай.
4. **Валидация семантики:**
   - `cube_sql` — какой SQL генерируется (гранулярность, joins, формула);
   - `cube_load` — число осмысленное, не пустое и не NULL-кованое;
   - YoY/PoP — только через готовые члены `sales_mov`, не пересчитывай в мере.
5. **Регресс:** `just test` и `just verify` (golden-вопросы + rows/SQL-паритет;
   `just cube` должен быть запущен). Новая метрика — добавь golden-случай в harness.
6. **Публикация** — git commit в ветке. Только когда пользователь явно просит.

## Conventions проекта

- `description`/`title` — на русском (язык вопросов), это канал бизнес-смысла агенту;
  имена членов — английские. Формулу и ограничения фиксируй в `description`, а не в чате.
- sql-выражение меры цитируй из требования пользователя («revenue после скидки,
  до налога» → так и в SQL, и в описании).
- Pre-aggregations: после правки смотри логи `just cube` — Cube сам скажет,
   совпадает ли rollup запросу (или запрос уходит в raw).
- Не трогай `warehouse/pocketstack.duckdb` руками: при остановках стека Cube держит
  блокировку DuckDB (`scripts/stack.sh down` перед reset, см. docs/gotchas.md).

## Если сломалось

| Симптом | Причина |
| --- | --- |
| Член не появляется в `cube_meta` | YAML не прошёл компиляцию — читай лог `just cube`, там файл и член |
| Число NULL/0 | Мера ссылается не на ту колонку — проверь `cube_sql` и витрину sqlmesh |
| `just verify` упал | Сломан паритет rows/SQL — golden-запрос против нового члена, сверись с harness |
| Conflicting lock (DuckDB) | Cube держит базу — останови стек перед пересборкой (docs/gotchas.md) |
| Собралось, но не queryable | Член не включён во view `sales` — проверь `includes` |
