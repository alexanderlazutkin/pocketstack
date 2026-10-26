# Подключение SQL-клиентов к Cube (DBeaver / DBX / любой pg-wire)

Cube отдаёт SQL API по протоколу PostgreSQL (pg-wire) на порт **15432**.
Любой клиент с драйвером PostgreSQL подключается к семантическому слою напрямую:
кубы выглядят как таблицы, метрики уже посчитаны Cube — запросы идут через ту же
семантику, что и дашборды Evidence (единый источник правды).

Проверено 2026-10-26: psql + интроспекция information_schema + SELECT \*.

## Параметры подключения

| Параметр | Значение |
|---|---|
| Host | `localhost` |
| Port | `15432` |
| Database | `default` |
| User | значение `CUBESQL_USER` из вашего `.env` |
| Password | значение `CUBESQL_PASSWORD` из вашего `.env` |
| SSL | выключить |

Креды задаются в `.env` (шаблон `.env.example`; пароль — `openssl rand -hex 32`).
Код фолбэков не содержит: без `.env` SQL API не примет дефолтные логин/пароль.

**Предусловие**: запущен Cube dev-сервер — `PATH=$HOME/.local/bin:$PATH just cube`
(REST :4000 + SQL API :15432). Без него подключения не будет.

## DBeaver

1. Database → New Connection → **PostgreSQL**
2. Заполнить параметры из таблицы выше (SSL вкладка — отключить)
3. Test Connection → Finish
4. В дереве: кубы появятся как таблицы схемы `public` (`sales_mov`, `fact_sales`,
   `dim_*`…), члены куба — как колонки

## DBX (и другие pg-клиенты)

Создать подключение типа PostgreSQL с теми же параметрами.
Куб представляется как `PostgreSQL 14.2 … cubesql` — совместимый клиент.

## Как писать запросы

Таблица = имя куба, колонка = `<куб>.<член>` (префикс куба обязателен, как в golden-SQL):

```sql
-- выручка по годам (мера revenue суммируется Cube)
SELECT sales_mov.year, SUM(sales_mov.revenue) AS revenue
FROM sales_mov GROUP BY 1 ORDER BY 1;

-- YoY/PoP-отклонения за 1997 (логика в кубе, не в клиенте)
SELECT sales_mov.month, sales_mov.revenue, sales_mov.revenue_ly,
       sales_mov.abs_yoy, sales_mov.rel_yoy, sales_mov.rel_pop
FROM sales_mov
WHERE sales_mov.year = 1997
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1;

-- каталог
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
```

### Нюансы (проверено)

- Агрегатные функции работают и по **мерам**, и по **измерениям**:
  `SUM(sales_mov.revenue)` (мера), `SUM(sales_mov.abs_yoy)` (измерение) — оба дают
  корректный rollup (для 1997: −103,374,792.92 = KPI дашборда, независимо подтверждает
  меру `abs_yoy_sum`). `AVG` по мере тоже валиден (средняя месячная выручка).
  Мismatch-ошибка возможна только для спец-мер (count_distinct и т.п.) — см. gotchas.
- `SELECT *` работает, но добавляет сервис-колонки `__user`, `__cubeJoinField`
  и агрегирует по ВСЕМ измерениям сразу — для читаемого вывода перечисляйте колонки.
- Диалект — подмножество pg: CTE и оконные функции работают;
  `AVG(дата − дата)` (interval) — нет (полный список: `docs/gotchas.md`, «SQL API Cube»).
- `LIMIT/ORDER BY/WHERE` — без ограничений.

## Отличие от Evidence

Дашборды Evidence читают **материализованные parquet** (DuckDB-WASM), а SQL-клиенты
попадают на **живой Cube** — при изменении данных (`just apply`) клиенты видят
новое сразу, дашборды после `npm run sources` (см. `docs/evidence-setup.md` §7).
