"""(b) Детерминизм SQL: POST /v1/sql → нормализация → sha256, N прогонов."""

import pytest
from harness.clients import CubeRestError, rest_sql
from harness.golden import GOLDEN
from harness.normalize import hash_sql

N_RUNS = 3


@pytest.mark.parametrize("g", GOLDEN, ids=[g["id"] for g in GOLDEN])
def test_sql_determinism(g, cube_up, results, CUBE_URL, CUBE_TOKEN):
    try:
        hashes = {hash_sql(rest_sql(CUBE_URL, CUBE_TOKEN, g["rest"])) for _ in range(N_RUNS)}
    except CubeRestError:
        results["determinism"][g["id"]] = False
        raise
    assert len(hashes) == 1, f"{N_RUNS} прогона дали {len(hashes)} разных SQL-хэшей"
    (h,) = hashes
    results["determinism"][g["id"]] = h
