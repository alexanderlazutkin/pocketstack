# Сравнение: Cube Core OSS vs eMondrian vs SSAS Multidimensional

> Подробное сравнение трёх движков аналитической семантики: современного semantic layer
> (Cube), OSS-наследника Mondrian (eMondrian) и эталонного классического OLAP
> (Microsoft SSAS Multidimensional). Актуально на октябрь 2026.
> Источники: [emondrian-community README](https://github.com/eMondrian/emondrian-community),
> [cube.dev/pricing](https://cube.dev/pricing), документация Microsoft Learn,
> инвентарь AW-куба в `ssasmd-cube-migration.md`.

Связанные доки: `cube-oss-vs-enterprise.md` (границы Cube OSS/Cloud),
`ssasmd-cube-migration.md` (миграция SSAS MD → Cube), `cube-mcp.md` (MCP-мост pocketstack).

## 1. TL;DR

| | Cube Core OSS | eMondrian Community | SSAS Multidimensional |
|---|---|---|---|
| **Что это** | Headless semantic layer: модель в YAML, SQL генерируется в витрину, API-first | ROLAP-сервер, продолжение Pentaho Mondrian: XMLA/MDX поверх реляционной БД | Эталон MOLAP-сервера: полный MDX, агрегаты в собственном хранилище |
| **Эволюция** | Активная разработка | Нишевая, маленькая команда (BIS) | Maintenance mode (входит в SQL Server, новых фич нет); стратегия Microsoft — Tabular/Fabric |
| **Основной потребитель** | Приложения, BI через SQL API, AI-агенты | Excel / ADOMD.NET-клиенты, AI-агенты (платно) | Excel, Power BI, SSRS — экосистема Microsoft |
| **Открытость** | Apache 2.0, ядро полностью открыто | EPL-1.0 ядро + **платные модули внутри Community** (DAX/Power BI, MCP) | Проприетарный, лицензия SQL Server (per-core) + Windows Server |
| **Вердикт** | Стандарт для API-first и git-native семантики | Окно в мир MDX/Excel для OSS-стека; проверять платные модули | Богатейшая OLAP-функциональность, но технологический тупик |

## 2. Позиционирование

```
        Классический OLAP (MDX / XMLA)                Семантический слой (API-first)
  ┌─────────────────────────────────────┬─────────────────────────────────────────┐
  │  SSAS Multidimensional              │  Cube Core OSS (Apache 2.0)             │
  │  • MOLAP/HOLAP/ROLAP, Windows       │  • YAML/JS-модель, git-native           │
  │  • полный MDX, SCOPE, KPI, actions  │  • REST / GraphQL / SQL (pg-wire)       │
  │  • rich security (cell-level)       │  • pre-aggregations + Cube Store        │
  │  • maintenance mode                 │  • активная разработка                  │
  ├─────────────────────────────────────┼─────────────────────────────────────────┤
  │  eMondrian Community                │  Cube Cloud (коммерческая надстройка:   │
  │  • ROLAP, XMLA/MDX без ключа        │  Semantic Layer Sync в Power BI/Tableau │
  │  • DAX (Power BI) и MCP — за ключ   │  Looker/Sheets, AI, SSO, аудит)         │
  │  • CE без аутентификации            │                                         │
  └─────────────────────────────────────┴─────────────────────────────────────────┘
```

SSAS MD и eMondrian живут в MDX/XMLA-мире (Excel-центричность), Cube — в мире,
где семантика потребляется программно. eMondrian — практически единственный живой
OSS-путь подключить Excel к собственному семантическому слою без SSAS.

## 3. Общие сведения

| Критерий | Cube Core OSS | eMondrian Community | SSAS Multidimensional |
|---|---|---|---|
| **Происхождение** | cube.js, open source с 2019, cube.dev | Fork/продолжение Mondrian (Julian Hyde ~2002 → Pentaho), поддерживает BIS Solutions; старый репозиторий `SergeiSemenkov/eMondrian` (war под Tomcat) заменён на `eMondrian/emondrian-community` | OLAP Services в SQL Server 7.0 (1999), затем Analysis Services; поставляется с SQL Server (вк. 2022) |
| **Язык/рантайм** | Node.js / TypeScript | Java (сервлет-контейнер, Docker) | Собственный Windows-сервис (C++) |
| **Модель данных** | Cubes/views (YAML/JS): меры, измерения, иерархии, join-ы | Схема Mondrian (XML): кубы, measure groups, иерархии, роли | Многомерная: measure groups, измерения, attribute/user hierarchies, переводы, перспективы |
| **Разработка модели** | Код-first (git, CI, dev-mode refresh) | XML-файлы + веб-редакторы schema/catalog в комплекте | Visual Studio (SSDT/Analysis Services projects), деплой XMLA/SSMS; артефакты в git — муторно |
| **Статус развития** | Активный (OSS 1.8.x) | Активный, нишевый | Поддерживается, без новых фич; Azure AS (только Tabular) объявлен к выводу в 2028 |

## 4. Языки запросов, протоколы, клиенты

| Критерий | Cube Core OSS | eMondrian Community | SSAS Multidimensional |
|---|---|---|---|
| **Язык запросов** | Собственный JSON Query Language + SQL через pg-wire | MDX (подмножество Mondrian) | Полный MDX (вкл. SCOPE-скрипты, CREATE SESSION MEMBER) |
| **Протоколы** | REST, GraphQL, SQL (Postgres wire, порт 15432 в pocketstack) | XMLA over SOAP (`/xmla`), REST `/api` | XMLA over TCP/HTTP(S), ADOMD.NET, AMO, TOM — нет |
| **Excel (PivotTable)** | ❌ напрямую нет; ⚠️ через SQL API как Postgres-источник | ✅ документированное подключение по XMLA | ✅ эталонная интеграция, лучший в классе pivot-опыт |
| **Power BI** | ⚠️ SQL API (pg-коннектор) или Semantic Layer Sync — Enterprise Cloud | ⚠️ Connect live требует платный модуль DAX (CSDL) | ✅ нативный live-коннектор (MDX→DAX трансляция, с ограничениями функций) |
| **Tableau** | ⚠️ через SQL API (pg) | ✅ документированное подключение | ✅ нативный коннектор MS Analysis Services |
| **Superset / Metabase** | ✅ как Postgres (pg-wire) | ❌ нет SQL-протокола | ❌ практического пути нет |
| **Свои приложения** | ✅ first-class (REST/GraphQL/SQL) | ⚠️ XMLA SOAP / REST API | ⚠️ ADOMD.NET (в осн. .NET-мир) |
| **SSRS / отчёты Microsoft** | ❌ | ❌ | ✅ |
| **AI-агенты (MCP)** | ⚠️ официально — Cube Cloud; self-host — свой мост (как `cube-mcp.md` в pocketstack) | ✅ встроенный MCP (streamable HTTP + SSE, 10 инструментов, audit-лог) — **требует licence key `MCP`** | ❌ (Copilot живёт в Power BI/Fabric, не в SSAS MD) |

Ключевое различие: **MDX — общий знаменатель SSAS MD и eMondrian** (миграция модели
между ними концептуально проще), тогда как Cube сознательно не реализует MDX/XMLA —
его семантика выражается через меры/измерения и потребляется по API.

## 5. Моделирование: функциональная матрица

Матрица классических OLAP-концепций (инвентарь реального куба AW — `ssasmd-cube-migration.md` §2).
Обозначения: ✅ нативно, ⚠️ частично/workaround, ❌ нет.

| Концепция | Cube Core OSS | eMondrian | SSAS MD | Комментарий |
|---|---|---|---|---|
| Меры sum / count / min / max / avg | ✅ | ✅ | ✅ | тривиально везде |
| count_distinct | ✅ | ✅ (MDX `DistinctCount`) | ✅ | |
| **Полуаддитивные меры** (LastNonEmpty, AverageOfChildren, ByAccount) | ⚠️ SQL-выражения на фикс. grain (`ssasmd-cube-migration.md` §3) | ❌ нет встроенных semi-additive агрегаторов | ✅ first-class (магия SSAS) | главный разрыв Cube↔SSAS |
| **Many-to-many измерения** | ⚠️ bridge-view + count-меры; суммы — только аллокация | ❌ нативных нет (Mondrian 3.x), workaround-ы | ✅ нативно | |
| **Parent-child иерархии** | ⚠️ flatten через closure-view (recursive CTE) | ✅ нативно (наследие Mondrian) | ✅ нативно + natural levels | |
| **Унарные операторы / custom rollup** (`+/-/~` в плане счетов) | ⚠️ эмуляция в closure-view: `Σ sign(op)·child` | ❌ (в Mondrian 3.x нет) | ✅ + custom member formulas | см. `ssasmd-cube-migration.md` §4 |
| **Calculated members «на любом срезе»** | ⚠️ ratio-меры через sum(num)/sum(den); семантика контекста MDX теряется | ✅ в схеме и в запросе | ✅ + **MDX-скрипт со SCOPE-присваиваниями** | SCOPE — уникальная возможность SSAS (валютная конверсия AW) |
| Named sets | ❌ (вне скоупа миграции) | ✅ | ✅ | |
| **KPI-объекты** (value/goal/status/trend) | ⚠️ метрика + `target`/`status_` в view | ❌ | ✅ wizard + MDX | |
| Actions / drillthrough | ❌ drillthrough — на стороне BI | ⚠️ MDX DRILLTHROUGH есть, actions нет | ✅ 16 actions в AW-кубе | |
| Perspectives (подпредставления куба) | ⚠️ решается отдельными views | ❌ | ✅ (5 в AW) | |
| Translations (локализация модели) | ⚠️ один язык в title/description | ❌ | ✅ (626 переводов в AW) | |
| Role-playing измерения (даты ×3) | ✅ многократный join одной таблицы | ✅ | ✅ | |
| Writeback (обратная запись в ячейки) | ❌ | ❌ | ✅ | планирование/budgeting-сценарии |
| **Ragged/несбалансированные иерархии** | ⚠️ через flatten | ⚠️ | ✅ (hide member if) | |

Итог по моделированию: **SSAS MD — сверхмощный OLAP-компилятор** (полуаддитивность,
M2M, SCOPE, унарные операторы — из коробки). **eMondrian** наследует ядро MDX-мира
Mondrian (parent-child, calculated members, named sets, DRILLTHROUGH), но без
semi-additive/M2M/SCOPE верхнего эшелона. **Cube** покрывает ~80% типовых нужд
(звезда, иерархии,role-playing, distinct count, ratio через деление агрегатов),
а оставшиеся 20% решаются SQL-ом на фикс. grain — с осознанной потерей
«семантики произвольного среза» MDX.

## 6. Производительность и ускорение запросов

| Механизм | Cube Core OSS | eMondrian | SSAS MD |
|---|---|---|---|
| **Агрегаты** | Pre-aggregations: rollup-таблицы строятся автоматически в БД-назначении или Cube Store | Aggregate tables Mondrian (наследование; design/caching заявлены в README) | Aggregation Designer + мастера, ручной дизайн партиций |
| **Хранение** | ROLAP: данные остаются в витрине (DuckDB/ClickHouse/…), агрегаты — рядом или в Cube Store (in-memory, OSS) | ROLAP: всегда SQL в исходную БД через JDBC; кэш результатов | **MOLAP** (по умолч.): собственное сжатое хранилище, HOLAP/ROLAP опционально |
| **Кэш** | In-memory + Cube Store | In-memory cache движка | Многоуровневый, + **proactive caching** (автообновление по данным) |
| **Партиционирование** | ⚠️ партиции pre-agg (time-split) | ❌ нет понятия партиций | ✅ партиции measure groups — ключ к TB-масштабу |
| **Масштаб** | Горизонтальный скейл API-нод; pre-agg в OLAP-БД | Ограничен исходной БД (ClickHouse даёт хороший потолок) | TB-масштабные кубы; query scale-out (реплики, 2019+) |
| **Свежесть данных** | Refresh-политики pre-agg (OSS) | Зависит от БД + инвалидация кэша | Proactive caching: от realtime до scheduled OLAP |

По характеру нагрузки: SSAS MD оптимален для **интерактивных Excel-pivot**
(агрегаты в памяти, мгновенный drill), eMondrian — для **деградации до SQL**
(производительность = производительность вашей БД), Cube — для **app-facing
sub-second API** (кэш + rollup, спроектирован под высокую конкурентность REST/SQL).

## 7. Безопасность

| Критерий | Cube Core OSS | eMondrian Community | SSAS MD |
|---|---|---|---|
| Аутентификация | ✅ JWT (генерация токенов в OSS) | ❌ **нет вообще в CE** (осознанно; README прямо предупреждает) | ✅ Windows/Kerberos |
| Авторизация по измерениям | ✅ access policies: member_level + row_level + member_masking (`cube-rbac.md`) | ⚠️ роли в схеме Mondrian XML (cube/hierarchy/level grants) | ✅ роли, dynamic security |
| **Cell-level security** | ❌ | ❌ | ✅ уникально |
| Multi-tenancy | ✅ security context / compile context (OSS) | ❌ | ⚠️ через dynamic security |
| SSO/SCIM | — Enterprise Cloud | — Enterprise-редакция eMondrian | ✅ (AD-экосистема) |

Важно: eMondrian CE публикует MCP на том же порту, что и всё остальное, без
аутентификации; 4 из 10 MCP-инструментов пишут состояние сервера (`save_schema`,
`save_catalog`) — README классифицирует доступ к порту как административный.

## 8. Эксплуатация и наблюдаемость

| Критерий | Cube Core OSS | eMondrian Community | SSAS MD |
|---|---|---|---|
| **Деплой** | npm / Docker / K8s; легко встроить в приложение | Docker Compose (~2 ГБ диск, ~700 МБ загрузка; front door на порту 80, ClickHouse в комплекте) | Windows Server + установка SQL Server AS; war/скриптов нет |
| **Платформа** | Linux/macOS/Windows, контейнеры | Linux/Windows + Docker | **только Windows** |
| **UI из коробки** | — (Cloud: IDE/Explore) | ✅ браузерный OLAP-клиент, schema-editor, catalog-editor, страница логов | SSMS, SQL Profiler |
| **Наблюдаемость** | Логи, `/readyz`; Query History — Cloud | `/logs`, **NDJSON audit-лог MCP** (IP усечены, секреты редуцированы, ротация 50 МБ) с рецептом Loki/ELK; Enterprise — Grafana из коробки | Flight recorder, XEvents, perf-счётчики Windows |
| **Обновление данных** | refresh воркеры pre-agg | перезагрузка/инвалидация кэша | processing (full/incremental), proactive caching |

## 9. Лицензии и стоимость

| Критерий | Cube Core OSS | eMondrian Community | SSAS MD |
|---|---|---|---|
| Лицензия ядра | Apache 2.0 | EPL-1.0 | Проприетарная (Microsoft) |
| **Что платно** | Cube Cloud (managed, sync, AI, SSO) — ядро OSS самодостаточно | **Модули внутри Community**: Power BI (DAX/CSDL) — ключ `DAX`; MCP — ключ `MCP`; `get_csdl` — оба. Free eval 30 дней | Лицензия SQL Server (per-core Standard/Enterprise) + Windows Server CALs/cores |
| Open-core-модель | Платят за хостинг и Enterprise-фичи | Платят за функции внутри открытой редакции | Не open-core |
| Vendor lock-in | Низкий (YAML + SQL в вашей БД) | Средний (схема Mondrian — стандарт де-факто OSS; платные модули — proprietary) | Высокий (Windows, proprietary формат, AMO) |

Практический вывод по деньгам: Cube OSS — $0 за весь функционал ядра;
eMondrian — $0 только если не нужны Power BI live и MCP (а MCP — одна из главных
фич редакции 2026 года); SSAS MD — стоимость SQL Server/Windows даже для одного куба.

## 10. Сильные и слабые стороны

### Cube Core OSS
- ✅ API-first (REST/GraphQL/SQL), git-native моделирование, CI-friendly
- ✅ Pre-aggregations + Cube Store в OSS; access policies (RBAC/RLS/masking) в OSS
- ✅ Мульти-БД, Apache 2.0, активная разработка
- ❌ Нет MDX/XMLA → нет прямого Excel; нет semi-additive/M2M/SCOPE-семантики
- ❌ AI/MCP официально — Cloud; self-host — свой мост

### eMondrian Community
- ✅ Единственный живой OSS-путь XMLA/MDX для Excel/Tableau на своей БД
- ✅ Веб-клиент и редакторы схемы из коробки; Docker за минуты
- ✅ MCP-сервер с audit-логом — редкость для ниши
- ❌ Ключевые фичи (Power BI, MCP) за платным ключом внутри «open»-редакции
- ❌ CE без аутентификации; pure ROLAP — потолок производительности = ваша БД
- ❌ Маленькая команда/комьюнити; MDX — подмножество Mondrian (без SCOPE и semi-additive)

### SSAS Multidimensional
- ✅ Богатейшая OLAP-семантика: semi-additive, M2M, SCOPE, унарные операторы, KPI, actions, translations, writeback, cell-level security
- ✅ MOLAP-производительность и масштаб (TB, партиции, proactive caching)
- ✅ Лучшая в мире Excel-интеграция
- ❌ Maintenance mode — будущее за Tabular/Fabric; Azure AS (Tabular-only) выводится в 2028
- ❌ Windows-only, дорого, проприетарно, модель в Visual Studio (не git-native)
- ❌ Нет SQL/REST API для приложений; AI-история вне самого продукта

## 11. Рекомендации по сценариям

| Сценарий | Выбор | Почему |
|---|---|---|
| Метрики для приложения/продукта, embed-аналитика | **Cube** | API-first, git-native, кэш/pre-agg под высокую конкурентность |
| Единая семантика для BI + AI-агентов в OSS-стеке | **Cube** (+ свой MCP-мост, см. `cube-mcp.md`) | MCP в eMondrian платен; SSAS MD вне OSS-мира |
| Организация живёт в Excel, БД своя (ClickHouse/Postgres/…) | **eMondrian** | XMLA для Excel без Microsoft-лицензий; Tableau тоже documented |
| Миграция с легаси-Mondrian/Pentaho | **eMondrian** | Совместимость схем Mondrian, знакомый FoodMart |
| Тяжёлый корпоративный фин. контур: планы счетов, унарные операторы, semi-additive, валютные SCOPE-пересчёты, writeback | **SSAS MD** (или миграция с потерями — `ssasmd-cube-migration.md`) | Никакой OSS-движок не воспроизводит эту семантику нативно |
| Already-in-Microsoft: Power BI, AD, SSRS | **SSAS MD** (пока поддерживается) / Tabular | Нативная интеграция, Kerberos, cell-level security |

## 12. Вывод для pocketstack

1. **Cube OSS остаётся правильным выбором** для демо-стека: SQL/REST API, Evidence,
   MCP для ИИ-агента — всё в OSS (см. `cube-oss-vs-enterprise.md`).
2. **eMondrian — не конкурент, а соседняя ниша**: если демо захочет «Excel-окно»
   поверх DuckDB/ClickHouse, это единственный OSS-путь — но MCP и Power BI там платны,
   а CE без auth, так что только локально/за доверенной сетью.
3. **SSAS MD используется как эталон полноты** при миграции AW-куба (`ssasmd-cube-migration.md`):
   карта §3 того документа фактически показывает цену отказа от SSAS MD — полуаддитивность,
   M2M и SCOPE-конверсии переходят в SQL на фиксированном grain.
