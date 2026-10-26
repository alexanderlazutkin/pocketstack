# Cube.dev: OSS vs Enterprise (Cube Cloud)

> Сравнение self-hosted версии Cube (open source, Apache 2.0) с управляемой Cube Cloud / Enterprise.
> Источник: [cube.dev/pricing](https://cube.dev/pricing) и официальная документация. Актуально на октябрь 2026.

## Есть в OSS (self-hosted)

| Возможность | OSS |
| --- | --- |
| Семантическое моделирование (cubes, views, меры, измерения) | ✅ |
| API: REST, GraphQL, SQL (pg-wire) | ✅ |
| Pre-aggregations (внешние rollup-таблицы) | ✅ |
| In-memory кэширование + Cube Store (OSS) | ✅ |
| Row-Level Security через security context | ✅ |
| JWT-аутентификация, генерация токенов | ✅ |
| Несколько источников данных, join across sources | ✅ |
| Deployment: Docker/K8s сами | ✅ |

## Отсутствует в OSS (только Cloud/Enterprise)

| Возможность | OSS | Enterprise |
| --- | --- | --- |
| Visual Semantic IDE / Data Model editor | — | ✅ |
| Workbooks, Explore, дашборды | — | ✅ |
| AI-агенты (semantic model agent, analytics chat) | — | ✅ |
| MCP server для AI-агентов | — | ✅ (докам Cloud) |
| **Semantic Layer Sync** (Power BI, Tableau, Looker, Sheets) | — | ✅ |
| dbt integration (генерация схем из dbt) | — | ✅ Premium+ |
| Query History + retention | — | ✅ (1–7 дней, Enterprise — custom) |
| Monitoring integrations (Datadog и т.п.) | — | ✅ Enterprise |
| SSO (Okta, SAML, SCIM) | — | ✅ Enterprise |
| Custom Roles, Explorer role | — | ✅ Enterprise |
| Audit Logging (полный аудит) | — | ✅ Enterprise |
| VPC Peering / AWS PrivateLink | — | ✅ Enterprise |
| Dedicated VPC / BYOC / BYOLLM | — | ✅ Enterprise |
| Managed multi-cluster, autoscaling, HA | — (самим через K8s) | ✅ |
| Managed Cube Store workers | — (самим) | ✅ |
| Поддержка (CSM, SLA) | community | ✅ |

## Лимиты Cube Cloud (для справки)

| Параметр | Free | Starter | Premium | Enterprise |
| --- | --- | --- | --- | --- |
| Запросов в день | 1 000 | 10K–50K | Unlimited | Unlimited |
| Workbooks | до 5 | Unlimited | Unlimited | Unlimited |
| Query history retention | 1 день | 1 день | 7 дней | Custom |

## Вывод для pocketstack

Ядро Cube (модели, API, pre-aggregations, RLS) полностью доступно в OSS — текущий стек
(кубы `sales` / `sales_mov`, REST + SQL API) ничего не теряет от self-hosted использования.

Enterprise добавляет: управляемость (UI/дашборды, sync в BI-инструменты, SSO/аудит,
наблюдаемость) и AI-фичи. Для closed-loop прогона в CI и MCP-интеграции достаточно OSS.

## Альтернативы Cube (open source)

- **dbt Core + MetricFlow** — трансформации + semantic layer, полностью OSS
- **Apache Superset** — OSS BI с упрощённым semantic layer

Классический OSS-стек: `Airflow/Dagster → dbt Core (+ MetricFlow) → Cube → Superset/Metabase`
на Postgres/Trino/ClickHouse как ядро хранения.
