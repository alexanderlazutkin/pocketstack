# Semantic Layer: Cube vs Dremio vs Hasura vs AtScale

> Сравнение функционала headless semantic layer / API-движков. Обновлено: 2026-11.

## Официальные ресурсы

| Инструмент | Сайт | GitHub | Лицензия |
|---|---|---|---|
| **Cube** | <https://cube.dev> | <https://github.com/cube-js/cube> | Apache 2.0 (core), Cloud — платный |
| **Dremio** | <https://www.dremio.com> | <https://github.com/dremio/dremio-oss> | Apache 2.0 (core), Enterprise — платный |
| **Hasura** | <https://hasura.io> | <https://github.com/hasura/graphql-engine> | Apache 2.0 (CE v2), Cloud/Enterprise — платные |
| **AtScale** | <https://www.atscale.com> | — (проприетарный) | Commercial |

Дополнительно:

- dbt MetricFlow (упомянут в контексте): <https://www.getdbt.com/product/dbt-semantic-layer> · <https://github.com/dbt-labs/metricflow>

---

## Категория (важно — они не прямые конкуренты)

| | Cube | Dremio | Hasura | AtScale |
|---|---|---|---|---|
| Класс | Headless semantic layer | SQL engine + semantic layer | GraphQL API engine над БД | Виртуализация + semantic layer для BI |
| Основная задача | Единые метрики как код, API-first | Быстрый SQL поверх data lake | Instant CRUD GraphQL/REST API | Быстрый SQL для Excel/Tableau/Power BI |

## Моделирование и семантика

| | Cube | Dremio | Hasura | AtScale |
|---|---|---|---|---|
| Метрики как код | Да — YAML/JS кубы, меры, измерения, view | Частично — VDs (виртуальные датасеты), но без богатых метрик | Нет — метрики вручную через SQL | Да — многомерные кубы, measures, hierarchies |
| Joins между сущностями | Да, включая many-to-many | Да (SQL) | Да, через relationship | Да (star schema) |
| Time-series метрики (YoY, rolling) | Из коробки (кубы `*_mov`) | Вручную SQL | Вручную | Частично (MDX-логика) |
| Multi-tenancy | Да, кубы на tenant | Нет (не для этого) | Да | Ограниченно |

## API и протоколы

| | Cube | Dremio | Hasura | AtScale |
|---|---|---|---|---|
| REST API | Да (`/v1/load`, Meta, SQL API) | Нет (SQL endpoint) | Да (REST auto-gen) | Нет |
| GraphQL | Да (родный) | Нет | Да — ядро продукта | Нет |
| SQL endpoint | Да (pg-wire, напр. `:15432`) | Да (ODBC/JDBC, Arrow Flight) | Нет | Да (генерирует SQL/MDX для BI) |
| ML/AI context (embeddings, LLM) | Да (Cube AI, MCP-ready) | Нет | Ограниченно | Нет |

## Производительность

| | Cube | Dremio | Hasura | AtScale |
|---|---|---|---|---|
| Pre-aggregations | Да, в external rollup-хранилища (ClickHouse, DuckDB, Redis) | Reflections (материализация) — очень мощные | Нет (только БД-индексы) | Aggregate awareness — динамический выбор агрегатов |
| Кэш | In-memory + external | Result cache + reflection | Нет встроенного | Да, intelligent |
| Pushdown query | Да | Да — сильнейший query planner | Да (простой) | Да (генерация оптимального SQL под целевой движок) |

## Источники данных

- **Cube**: любые SQL-БД, BigQuery, Snowflake, ClickHouse и др.; rollup в external store. <https://cube.dev/docs/connect>
- **Dremio**: file/lake (Parquet, Iceberg, Delta), HDFS/S3, реляционные БД — читает напрямую из lake без загрузки. <https://docs.dremio.com/current/sonar/sources>
- **Hasura**: реляционные БД (Postgres, MySQL, SQL Server, CockroachDB); в v3 — Data Connectors. <https://hasura.io/docs/databases>
- **AtScale**: major warehouses (Snowflake, BigQuery, Redshift, Synapse, Databricks) — работает поверх warehouse, не хранит данные. <https://www.atscale.com/data-warehouse-connectors>

## Безопасность

| | Cube | Dremio | Hasura | AtScale |
|---|---|---|---|---|
| RLS / multi-tenant security context | Да (securityContext, member-level) | Да (basic) | Да — очень зрелая (row/column-level permissions) | Да (роли, cell-level) |
| SSO/IdP | Cloud / свои integrations | Enterprise | Enterprise (в CE ограничено) | Enterprise |

## Интеграции с BI

- **Cube**: работает как источник для любых BI через SQL endpoint; родных визуализаций нет. <https://cube.dev/integrations>
- **Dremio**: прямой коннект Tableau/Power BI/Superset. <https://www.dremio.com/platform/bi-tools>
- **Hasura**: не BI-инструмент — для приложений.
- **AtScale**: сильнейший — «говорит на MDX» для Excel, native для Tableau/Power BI. <https://www.atscale.com/bi-tool-integrations>

---

## Итог — что выбрать

| Задача | Выбор |
|---|---|
| Единые метрики для API, дашбордов, AI-агентов (headless) | **Cube** |
| Тяжёлый SQL поверх data lake/Iceberg без загрузки в warehouse | **Dremio** |
| Быстрый backend API для приложения (GraphQL/REST) | **Hasura** |
| Ускорить существующие Excel/Tableau/Power BI отчёты без переделки | **AtScale** |

## Контекст pocketstack

Cube покрывает semantic layer полностью; Hasura мог бы быть дополнением как app-API слой (не замена); Dremio/AtScale избыточны — они решают другую задачу (query engine / BI-ускорение).
