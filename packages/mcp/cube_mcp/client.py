"""Тонкий слой доступа к Cube для MCP-tools: REST (:4000) + pg-wire SQL API (:15432).

Креды — из .env (harness.env.load_env): в коде секретов нет.
REST-токен: CUBEJS_API_TOKEN (готовый JWT любой роли, см. scripts/make-cube-token.py)
или admin-JWT, автоматически подписанный на CUBEJS_API_SECRET (прод-режим Cube
принимает только JWT — сырой секрет даёт 403; RBAC — docs/cube-rbac.md).
Все функции возвращают JSON-строку — так их отдаёт MCP-клиенту FastMCP.
"""

import json
import os
import time

import psycopg
import requests
from harness.env import load_env, required
from harness.tokens import mint_cube_token

load_env()

BASE = os.environ.get("CUBEJS_URL", "http://localhost:4000")
TOKEN = os.environ.get("CUBEJS_API_TOKEN") or mint_cube_token(
    required("CUBEJS_API_SECRET"), {"groups": ["admin"]}, ttl_seconds=12 * 3600
)
SQLAPI = {
    "host": os.environ.get("CUBESQL_HOST", "localhost"),
    "port": int(os.environ.get("CUBESQL_PORT", "15432")),
    "user": required("CUBESQL_USER"),
    "password": required("CUBESQL_PASSWORD"),
    "dbname": "default",
}

_TIMEOUT = 60
_READONLY_PREFIXES = ("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN")
_MAX_ROWS_CAP = 200


def _post(path: str, body: dict) -> dict:
    r = requests.post(
        f"{BASE}/cubejs-api/v1/{path}",
        json=body,
        headers={"Authorization": TOKEN},
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Cube {path} → HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _query(measures, dimensions, filters, limit) -> dict:
    if not measures:
        raise ValueError("measures не пустой список, например ['sales.revenue']")
    q: dict = {"measures": list(measures)}
    if dimensions:
        q["dimensions"] = list(dimensions)
    if filters:
        q["filters"] = list(filters)
    if limit:
        q["limit"] = int(limit)
    return q


def cube_meta() -> str:
    """Кубы/меры/измерения семантического слоя (GET /meta)."""
    r = requests.get(
        f"{BASE}/cubejs-api/v1/meta", headers={"Authorization": TOKEN}, timeout=_TIMEOUT
    )
    if r.status_code != 200:
        raise RuntimeError(f"Cube meta → HTTP {r.status_code}: {r.text[:300]}")
    return json.dumps(r.json(), ensure_ascii=False)


def cube_load(measures, dimensions=None, filters=None, limit=None) -> str:
    """Выполнить запрос через REST /v1/load с renewQuery=true (мимо кэша Cube)."""
    started = time.perf_counter()
    out = _post("load", {"query": _query(measures, dimensions, filters, limit), "renewQuery": True})
    rows = out.get("data", [])
    return json.dumps(
        {
            "rows": rows,
            "row_count": len(rows),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "cache_bypassed": True,
        },
        ensure_ascii=False,
    )


def cube_sql(measures, dimensions=None, filters=None, limit=None) -> str:
    """Показать SQL, который Cube сгенерирует для запроса (БЕЗ исполнения)."""
    out = _post("sql", {"query": _query(measures, dimensions, filters, limit)})
    # контракт /v1/sql: {"sql": {"sql": ["SELECT ...", [params]], ...}}
    wrapper = out.get("sql", {})
    raw = wrapper.get("sql", wrapper) if isinstance(wrapper, dict) else wrapper
    if isinstance(raw, list):
        sql_text = next((p for p in raw if isinstance(p, str)), str(raw))
    else:
        sql_text = str(raw)
    return json.dumps({"sql": sql_text, "executed": False}, ensure_ascii=False)


def sql_api(sql: str, max_rows: int = 50) -> str:
    """Read-only SQL через pg-wire SQL API Cube (:15432). Только SELECT/WITH/SHOW/DESCRIBE/EXPLAIN."""
    normalized = sql.strip().upper()
    if not normalized.startswith(_READONLY_PREFIXES):
        raise ValueError(
            f"sql_api — read-only: только {', '.join(_READONLY_PREFIXES)} (получено: {sql[:60]!r})"
        )
    max_rows = min(int(max_rows), _MAX_ROWS_CAP)
    started = time.perf_counter()
    with psycopg.connect(**SQLAPI) as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [d.name for d in cur.description]
        rows = cur.fetchmany(max_rows)
    return json.dumps(
        {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "note": f"показано до {max_rows} строк",
        },
        ensure_ascii=False,
        default=str,
    )
