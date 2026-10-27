"""Фикстуры harness: пути, клиенты, сбор результатов, markdown-отчёт."""

import os
import sys
from pathlib import Path

import pytest
from harness.env import load_env, required
from harness.tokens import mint_cube_token

load_env()  # .env из корня репо: секреты не в коде (см. .env.example)

# Токен admin для REST: JWT, подписанный CUBEJS_API_SECRET. Прод-режим Cube
# (RBAC, docs/cube-rbac.md) принимает только подписанные JWT — сырой секрет → 403.
CUBE_TOKEN_VALUE = mint_cube_token(
    required("CUBEJS_API_SECRET"), {"groups": ["admin"]}, ttl_seconds=12 * 3600
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"
ARTIFACTS = REPO / "artifacts"
QUERY_LOG = ARTIFACTS / "duckdb_query_log.csv"
REPORT = ARTIFACTS / "verify-report.md"

CUBE_URL_VALUE = os.environ.get("CUBEJS_URL", "http://localhost:4000")
SQLAPI_DSN = {
    "host": os.environ.get("CUBESQL_HOST", "localhost"),
    "port": int(os.environ.get("CUBESQL_PORT", "15432")),
    "user": required("CUBESQL_USER"),
    "password": required("CUBESQL_PASSWORD"),
    "dbname": "default",
}
STRICT = os.environ.get("HARNESS_STRICT", "") == "1"


def _cube_reachable(base: str) -> bool:
    import requests

    try:
        # прод-режим (RBAC): /meta без подписанного JWT даёт 403 — идём с токеном admin
        r = requests.get(
            f"{base}/cubejs-api/v1/meta",
            headers={"Authorization": CUBE_TOKEN_VALUE},
            timeout=3,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def CUBE_URL():
    return CUBE_URL_VALUE


@pytest.fixture(scope="session")
def CUBE_TOKEN():
    return CUBE_TOKEN_VALUE


@pytest.fixture(scope="session")
def cube_up():
    if not _cube_reachable(CUBE_URL_VALUE):
        msg = f"Cube недоступен на {CUBE_URL_VALUE}: запустите `just cube`"
        if STRICT:
            raise RuntimeError(msg)
        pytest.skip(msg)


@pytest.fixture(scope="session")
def duckdb_con():
    import duckdb

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def sqlapi_conn(cube_up):
    import psycopg

    conn = psycopg.connect(**SQLAPI_DSN)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def query_log_path():
    return QUERY_LOG


@pytest.fixture(scope="session")
def results():
    """Сбор пер-вопросных итогов для verify-report.md."""
    collected = {"parity": {}, "determinism": {}, "ground_truth": {}}
    yield collected
    from harness.report import write_report

    write_report(collected, REPORT)
