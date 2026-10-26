# MCP-сервер pocketstack/cube

Тонкий MCP-сервер (stdio) вокруг семантического слоя Cube — Stage 5 плана.

**Почему свой**: официального MCP-пакета у Cube нет (`@cubejs-backend/mcp` — 404,
галлюцинированное имя); `/mcp` — endpoint Enterprise/Cube Cloud, к локальному
OSS-Cube неприменим (проверено: `localhost:4000/mcp` → 404). Поэтому — обёртка
над существующими API, теми же путями, что проверяет harness.

## Инструменты (все read-only)

| Tool | Куб | Что делает |
|---|---|---|
| `cube_meta` | `GET /cubejs-api/v1/meta` | кубы/меры/измерения — с этого начинать |
| `cube_load` | `POST /v1/load` + `renewQuery: true` | выполнить запрос **мимо кэша**; ответ: rows, row_count, duration_ms |
| `cube_sql` | `POST /v1/sql` | показать SQL, который Cube сгенерирует (без исполнения) — ground-truth стиль |
| `sql_api` | pg-wire `:15432` | произвольный read-only SQL (только SELECT/WITH/SHOW/DESCRIBE/EXPLAIN, лимит 200 строк) |

Креды — из `.env` (`CUBEJS_API_SECRET`, `CUBESQL_USER`, `CUBESQL_PASSWORD` через
`harness.env`); сервер сам их загружает — в конфиге клиента секретов нет.

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
list_tools + call_tool. Требует живого Cube (`scripts/stack.sh up`) и `.env`.

## Пример сессии агента

1. `cube_meta()` → видит кубы `sales`, `sales_mov` и их членов.
2. `cube_load(measures=["sales_mov.revenue"], dimensions=["sales_mov.month"], filters=[{"member": "sales_mov.year", "operator": "equals", "values": ["1997"]}])` → 12 строк.
3. `cube_sql(...)` → показывает SQL с CTE/self-join — агент объясняет семантику YoY/PoP, не придумывая формулы.

Отклонения/метрики считаются в **Cube** — агент только вызывает готовых членов
(instructions сервера это прямо требуют).
