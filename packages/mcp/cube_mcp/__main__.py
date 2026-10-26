"""python -m cube_mcp — stdio MCP-сервер (вызывается MCP-клиентом)."""

from cube_mcp.server import mcp

mcp.run(transport="stdio")
