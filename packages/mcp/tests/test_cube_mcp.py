"""TDD-тесты MCP-сервера вокруг Cube (Stage 5).

Два уровня:
- unit: вызов tool-функций напрямую (без MCP-протокола);
- e2e: спавн stdio-сервера + настоящий MCP-клиент SDK (list_tools + call_tool).
"""

import json

import pytest

from cube_mcp.client import cube_load, cube_meta, cube_sql, sql_api


def test_meta_lists_cubes(cube_up):
    meta = json.loads(cube_meta())
    cubes = {c["name"] for c in meta["cubes"]}
    assert {"sales", "sales_mov"} <= cubes
    sales = next(c for c in meta["cubes"] if c["name"] == "sales")
    members = {m["name"] for m in sales["measures"]} | {d["name"] for d in sales["dimensions"]}
    # имена членов в /meta — полные (куб.член)
    assert "sales.revenue" in members


def test_load_returns_rows_without_cache(cube_up):
    out = json.loads(cube_load(measures=["sales.revenue"], dimensions=["sales.customer_region"]))
    assert out["row_count"] == 5
    assert out["cache_bypassed"] is True
    assert out["duration_ms"] >= 0
    # ключи строк — полные имена членов
    assert all("sales.revenue" in r for r in out["rows"])


def test_load_with_filter_and_limit(cube_up):
    out = json.loads(
        cube_load(
            measures=["sales.revenue"],
            dimensions=["sales.month"],
            filters=[{"member": "sales.year", "operator": "equals", "values": ["1996"]}],
        )
    )
    assert out["row_count"] == 12


def test_sql_shows_compiled_sql_without_executing(cube_up):
    out = json.loads(cube_sql(measures=["sales.revenue"]))
    sql = out["sql"].lower()
    assert "select" in sql and "sum(" in sql
    assert "executed" in out and out["executed"] is False


class TestSqlApiValidation:
    def test_rejects_writes(self):
        for bad in ("DELETE FROM sales", "INSERT INTO t VALUES (1)", "DROP TABLE x"):
            with pytest.raises(ValueError, match="read-only|SELECT"):
                sql_api(bad)

    def test_rows_and_columns(self, cube_up):
        out = json.loads(sql_api("SELECT sales.year, SUM(sales.revenue) FROM sales GROUP BY 1"))
        assert out["row_count"] == 7
        assert out["columns"][0] == "year"
        assert "revenue" in out["columns"][1].lower()  # неалиасованный агрегат
        assert out["duration_ms"] >= 0

    def test_max_rows_cap(self, cube_up):
        out = json.loads(sql_api("SELECT part_type FROM sales GROUP BY 1", max_rows=3))
        assert out["row_count"] <= 3


def test_secret_not_required_in_code_paths(cube_up):
    """Креды берутся из окружения (.env): токен не входит в ответы инструментов."""
    out = json.loads(cube_meta())
    blob = json.dumps(out)
    import os

    assert os.environ["CUBEJS_API_SECRET"] not in blob
