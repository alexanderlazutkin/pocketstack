"""Stage 2 acceptance: REST /v1/load vs SQL API (pg-wire) vs DuckDB reference."""

import json
import os
import subprocess
import urllib.request

import duckdb

WAREHOUSE = "/home/lan/Git/DE/pocketstack/warehouse/pocketstack.duckdb"


def rest_query() -> dict:
    body = json.dumps(
        {
            "query": {
                "measures": ["fact_sales.revenue"],
                "dimensions": ["dim_customer.customer_region"],
            }
        }
    ).encode()
    req = urllib.request.Request(
        "http://localhost:4000/cubejs-api/v1/load",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)["data"]
    return {
        row["dim_customer.customer_region"]: round(float(row["fact_sales.revenue"]), 2)
        for row in data
    }


def sql_api_query() -> dict:
    from harness.env import load_env

    load_env()  # креды из .env (см. .env.example)
    out = subprocess.run(
        [
            "psql",
            "-h",
            os.environ.get("CUBESQL_HOST", "localhost"),
            "-p",
            os.environ.get("CUBESQL_PORT", "15432"),
            "-U",
            os.environ["CUBESQL_USER"],
            "-d",
            "default",
            "-At",
            "-F",
            "|",
            "-c",
            ('SELECT "customer_region", SUM("revenue") FROM "sales" '
            'GROUP BY "customer_region" ORDER BY "customer_region"'),
        ],
        capture_output=True,
        text=True,
        env={
            "PGPASSWORD": os.environ.get(
                "CUBESQL_PASSWORD", ""
            ),  # из .env; см. harness.env.load_env и .env.example
            "PATH": "/usr/bin:/bin",
        },
        check=True,
    ).stdout
    result = {}
    for line in out.strip().splitlines():
        region, revenue = line.split("|")
        result[region] = round(float(revenue), 2)
    return result


def reference() -> dict:
    con = duckdb.connect(WAREHOUSE, read_only=True)
    try:
        rows = con.execute(
            "SELECT d.customer_region, SUM(f.net_price) "
            "FROM marts.fact_sales f JOIN marts.dim_customer d "
            "ON d.customer_id = f.customer_id GROUP BY 1"
        ).fetchall()
    finally:
        con.close()
    return {r: round(float(v), 2) for r, v in rows}


if __name__ == "__main__":
    a, b, c = rest_query(), sql_api_query(), reference()
    print(f"{'REST':<30} SQL-API{'':<24} REFERENCE")
    for region in sorted(c):
        print(f"{region:<30} {a.get(region)}{'':<24} {b.get(region)} | {c[region]}")
    assert a == b == c, f"MISMATCH: rest={a} sql={b} ref={c}"
    print(f"\nOK: {len(c)} строк идентичны по всем трём путям")
