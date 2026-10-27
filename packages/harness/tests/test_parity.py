"""(a) Rows-паритет: /v1/load vs SQL API (pg-wire) vs reference DuckDB."""

import pytest
from harness.clients import reference_query, rest_load, rows_rest, sqlapi_query
from harness.golden import GOLDEN
from harness.normalize import norm_rows


@pytest.mark.parametrize("g", GOLDEN, ids=[g["id"] for g in GOLDEN])
def test_rows_parity(g, cube_up, duckdb_con, sqlapi_conn, results, CUBE_URL, CUBE_TOKEN):
    rest_rows = rows_rest(rest_load(CUBE_URL, CUBE_TOKEN, g["rest"]), g["rest"])
    api_rows = sqlapi_query(sqlapi_conn, g["sqlapi"])
    ref_rows = reference_query(duckdb_con, g["reference"])

    k = g["key_cols"]
    a = norm_rows(rest_rows, k)
    b = norm_rows(api_rows, k)
    c = norm_rows(ref_rows, k)
    if not g.get("ordered"):
        a, b, c = sorted(a), sorted(b), sorted(c)

    assert len(a) == len(b) == len(c), f"rowcount: REST={len(a)} SQLAPI={len(b)} REF={len(c)}"
    assert a == b, f"REST != SQLAPI:\n{a[:3]}\n{b[:3]}"
    assert b == c, f"SQLAPI != REF:\n{b[:3]}\n{c[:3]}"
    results["parity"][g["id"]] = True
