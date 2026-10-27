"""Фикстуры MCP-тестов: живой Cube (как в harness) + .env."""

import os
import sys
from pathlib import Path

import pytest
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # packages/ для импорта harness.*

from harness.env import load_env, required
from harness.tokens import mint_cube_token

load_env()

CUBE_URL = os.environ.get("CUBEJS_URL", "http://localhost:4000")
# Прод-режим Cube (RBAC): /meta без подписанного JWT даёт 403 — пингуем токеном admin.
TOKEN = mint_cube_token(required("CUBEJS_API_SECRET"), {"groups": ["admin"]}, ttl_seconds=12 * 3600)


@pytest.fixture(scope="session")
def cube_up():
    try:
        r = requests.get(
            f"{CUBE_URL}/cubejs-api/v1/meta", headers={"Authorization": TOKEN}, timeout=3
        )
        assert r.status_code == 200
    except (OSError, AssertionError) as e:  # pragma: no cover
        pytest.exit(f"Cube недоступен на {CUBE_URL} — запустите scripts/stack.sh up ({e})")
    return CUBE_URL
