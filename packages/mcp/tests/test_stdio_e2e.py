"""E2E: stdio-транспорт — спавним сервер как это делает opencode/Claude Code."""

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.anyio

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_stdio_list_tools_and_call_meta():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cube_mcp"],
        cwd=str(REPO),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"cube_meta", "cube_load", "cube_sql", "sql_api"} <= names

            result = await session.call_tool("cube_meta", {})
            payload = json.loads(result.content[0].text)
            cubes = {c["name"] for c in payload["cubes"]}
            assert "sales" in cubes
