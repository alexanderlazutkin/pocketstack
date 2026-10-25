"""Клиенты трёх путей выполнения: Cube REST, Cube SQL API (pg-wire), DuckDB reference."""

import time

import requests

REST_TIMEOUT = 90
POLL_DELAY = 1.5


class CubeRestError(RuntimeError):
    pass


def rest_load(base: str, token: str, query: dict, renew: bool = False) -> list[dict]:
    """POST /v1/load с поллингом до готовности. Возвращает data-строки."""
    body = {"query": query}
    if renew:
        body["renewQuery"] = True
    deadline = time.time() + REST_TIMEOUT
    while time.time() < deadline:
        r = requests.post(
            f"{base}/cubejs-api/v1/load",
            json=body,
            headers={"Authorization": token},
            timeout=30,
        )
        payload = r.json()
        t = payload.get("type", "")
        if "data" in payload:  # готово (кэш может не отдавать type=".query")
            return payload["data"]
        if t == "Query is in progress" or t == "queryRestartedError":
            time.sleep(POLL_DELAY)
            continue
        raise CubeRestError(f"/v1/load {t or r.status_code}: {payload.get('error', payload)}")
    raise CubeRestError(f"/v1/load: таймаут {REST_TIMEOUT}s")


def rest_sql(base: str, token: str, query: dict) -> str:
    """POST /v1/sql → основной SELECT (pre-aggregations выключены)."""
    r = requests.post(
        f"{base}/cubejs-api/v1/sql",
        json={"query": query},
        headers={"Authorization": token},
        timeout=30,
    )
    payload = r.json()
    if r.status_code != 200 or "sql" not in payload:
        raise CubeRestError(f"/v1/sql: {payload.get('error', payload)}")
    return payload["sql"]["sql"][0]


def sqlapi_query(conn, sql: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def reference_query(con, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def rows_rest(data: list[dict], query: dict) -> list[tuple]:
    """/v1/load data → кортежи (значения dimensions по порядку запроса, затем measures)."""
    dims = query.get("dimensions", [])
    meas = query.get("measures", [])
    return [tuple(row[f"{m}"] for m in dims + meas) for row in data]
