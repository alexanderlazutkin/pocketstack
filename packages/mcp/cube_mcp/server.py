"""MCP-сервер pocketstack/cube (stdio): тонкая обёртка над Cube REST + SQL API.

Запуск (его делает MCP-клиент — opencode/Claude Code):
    python -m cube_mcp
Документация: docs/cube-mcp.md
"""

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cube_mcp import client

logging.basicConfig(
    stream=sys.stderr, level=logging.INFO, format="%(asctime)s cube-mcp %(levelname)s %(message)s"
)

mcp = FastMCP(
    "cube",
    instructions=(
        "Семантический слой pocketstack (Cube). Метрики уже определены в кубах "
        "sales и sales_mov — не придумывай формулы, вызывай готовые члены "
        "(cube_meta). Отклонения YoY/PoP считаются кубом sales_mov, а не агентом. "
        "Для проверки «какой SQL сгенерирует Cube» используй cube_sql."
    ),
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def cube_meta() -> str:
    """Кубы/меры/измерения семантического слоя Cube (JSON).
    Начинай отсюда: имена кубов и членов для cube_load/cube_sql."""
    return client.cube_meta()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def cube_load(
    measures: list[str],
    dimensions: list[str] | None = None,
    filters: list[dict] | None = None,
    limit: int | None = None,
) -> str:
    """Выполнить запрос к Cube (REST /v1/load, мимо кэша).

    Args:
        measures: члены-меры, напр. ["sales.revenue"]
        dimensions: измерения для группировки, напр. ["sales.customer_region"]
        filters: фильтры Cube, напр. [{"member": "sales.year", "operator": "equals", "values": ["1997"]}]
        limit: ограничение строк
    """
    return client.cube_load(measures, dimensions, filters, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def cube_sql(
    measures: list[str],
    dimensions: list[str] | None = None,
    filters: list[dict] | None = None,
    limit: int | None = None,
) -> str:
    """Показать SQL, который Cube сгенерирует для запроса (без исполнения) —
    для ground-truth проверки и объяснения семантики."""
    return client.cube_sql(measures, dimensions, filters, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def sql_api(sql: str, max_rows: int = 50) -> str:
    """Исполнить read-only SQL через pg-wire SQL API Cube (:15432).

    Таблица = имя куба, колонка = 'куб.член'. Только SELECT/WITH/SHOW/DESCRIBE/EXPLAIN.

    Args:
        sql: запрос, напр. SELECT sales.year, SUM(sales.revenue) FROM sales GROUP BY 1
        max_rows: максимум строк (до 200)
    """
    return client.sql_api(sql, max_rows)


if __name__ == "__main__":
    mcp.run(transport="stdio")
