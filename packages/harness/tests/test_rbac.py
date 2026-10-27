"""RBAC-матрица «Admin vs User»: REST /v1/meta + /v1/load, SQL API :15432, MCP-клиент.

Политики описаны в модели (views/sales.view.yml + кубы fact_sales/sales_mov),
группы назначает contextToGroups в cube.js из подписанных claims
(docs/cube-rbac.md). Демо-сценарий:
  admin — все меры/измерения, все регионы;
  user  — ровно 3 меры (revenue, quantity, orders_count) и только свой регион.
"""

import importlib
import json
import os
import random
from datetime import UTC, datetime

import psycopg
import pytest
import requests
from harness.clients import CubeRestError, rest_load
from harness.env import required
from harness.tokens import mint_cube_token, verify_cube_token

ALL_MEASURES = {
    "sales.revenue",
    "sales.revenue_with_tax",
    "sales.quantity",
    "sales.lines_count",
    "sales.orders_count",
    "sales.avg_discount",
}
USER_MEASURES = {"sales.revenue", "sales.quantity", "sales.orders_count"}
REGIONS = {"AFRICA", "AMERICA", "ASIA", "EUROPE", "MIDDLE EAST"}
# SQL API: таблица = имя витрины, колонка = 'куб.член'
SQLAPI_REGION_QUERY = "SELECT sales.customer_region, SUM(sales.revenue) FROM sales GROUP BY 1"
SQLAPI_FORBIDDEN = "SELECT AVG(sales.avg_discount) FROM sales"


# --- инфраструктура -----------------------------------------------------------


def _meta(base: str, token: str) -> dict:
    r = requests.get(f"{base}/cubejs-api/v1/meta", headers={"Authorization": token}, timeout=60)
    assert r.status_code == 200, f"/meta HTTP {r.status_code}: {r.text[:300]}"
    cubes = r.json()["cubes"]
    if isinstance(cubes, list):  # новый формат meta — список
        cubes = {c["name"]: c for c in cubes}
    return cubes


def _measures(entry: dict | None) -> set[str]:
    return {m["name"] for m in (entry or {}).get("measures", [])}


def _dims(entry: dict | None) -> set[str]:
    return {d["name"] for d in (entry or {}).get("dimensions", [])}


def _user_region() -> str:
    return os.environ.get("CUBE_RBAC_USER_REGION", "AFRICA")


@pytest.fixture(scope="session")
def user_region(cube_up):
    return _user_region()


@pytest.fixture(scope="session")
def api_secret(cube_up):
    """Сырой CUBEJS_API_SECRET — им ПОДПИСЫВАЮТСЯ role-JWT (CUBE_TOKEN — уже готовый JWT admin)."""
    return required("CUBEJS_API_SECRET")


@pytest.fixture(scope="session")
def admin_jwt(api_secret):
    return mint_cube_token(api_secret, {"groups": ["admin"]}, ttl_seconds=3600)


@pytest.fixture(scope="session")
def user_jwt(api_secret, user_region):
    return mint_cube_token(
        api_secret, {"groups": ["user"], "region": user_region}, ttl_seconds=3600
    )


@pytest.fixture(autouse=True, scope="session")
def require_prod_mode(cube_up, CUBE_URL):
    """RBAC работает только в прод-режиме: dev отключает авторизацию целиком.

    Проба: сырой CUBEJS_API_SECRET в проде даёт 403; в dev-режиме любой
    токен принимается (200) → все RBAC-тесты пропускаются.
    Прод: `just cube-prod`; dev (по умолчанию, playground): `just cube`.
    """
    r = requests.get(
        f"{CUBE_URL}/cubejs-api/v1/meta",
        headers={"Authorization": required("CUBEJS_API_SECRET")},
        timeout=30,
    )
    if r.status_code != 403:
        pytest.skip(
            f"Cube в dev-режиме (auth отключён, raw secret → HTTP {r.status_code}); нужен `just cube-prod`"
        )


@pytest.fixture(scope="session")
def nogroup_jwt(api_secret):
    return mint_cube_token(api_secret, {}, ttl_seconds=3600)


@pytest.fixture(scope="session")
def sqlapi_user_conn(cube_up):
    conn = psycopg.connect(
        host=os.environ.get("CUBESQL_HOST", "localhost"),
        port=int(os.environ.get("CUBESQL_PORT", "15432")),
        user=required("CUBESQL_RBAC_USER"),
        password=required("CUBESQL_RBAC_PASSWORD"),
        dbname="default",
    )
    yield conn
    conn.close()


# --- 1. REST /v1/meta: состав членов по ролям ---------------------------------


def test_rest_raw_secret_rejected(cube_up, CUBE_URL):
    """Прод-режим: сырой CUBEJS_API_SECRET (не JWT) отклоняется — 403."""
    r = requests.get(
        f"{CUBE_URL}/cubejs-api/v1/meta",
        headers={"Authorization": required("CUBEJS_API_SECRET")},
        timeout=30,
    )
    assert r.status_code == 403


def test_meta_admin_jwt_all_members(cube_up, CUBE_URL, admin_jwt):
    cubes = _meta(CUBE_URL, admin_jwt)
    assert _measures(cubes.get("sales")) == ALL_MEASURES
    assert "sales.avg_discount" in _measures(cubes.get("sales"))


def test_meta_user_exactly_three_measures(cube_up, CUBE_URL, admin_jwt, user_jwt):
    admin, user = _meta(CUBE_URL, admin_jwt), _meta(CUBE_URL, user_jwt)
    assert _measures(user.get("sales")) == USER_MEASURES
    assert "sales.avg_discount" not in _measures(user.get("sales"))
    # измерения остаются доступны целиком — группировать можно
    assert _dims(user.get("sales")) == _dims(admin.get("sales"))
    assert "sales.customer_region" in _dims(user.get("sales"))


def test_meta_user_direct_fact_cubes_denied(cube_up, CUBE_URL, user_jwt):
    """Мимо витрины: прямые кубы факта/движений для user закрыты (deny by default)."""
    cubes = _meta(CUBE_URL, user_jwt)
    assert not _measures(cubes.get("fact_sales")) and not _dims(cubes.get("fact_sales"))
    assert not _measures(cubes.get("sales_mov")) and not _dims(cubes.get("sales_mov"))


def test_meta_nogroup_denied(cube_up, CUBE_URL, nogroup_jwt):
    """Подписанный токен без групп → ничего (deny by default)."""
    cubes = _meta(CUBE_URL, nogroup_jwt)
    assert not _measures(cubes.get("sales"))


def test_meta_dual_group_union(cube_up, CUBE_URL, api_secret):
    """Юзер в двух группах: члены объединяются (union), а не пересекаются."""
    dual = mint_cube_token(api_secret, {"groups": ["admin", "user"]}, ttl_seconds=600)
    cubes = _meta(CUBE_URL, dual)
    assert _measures(cubes.get("sales")) == ALL_MEASURES


# --- 2. REST /v1/load: строки и меры по ролям ---------------------------------


def _revenue_by_region(base: str, token: str) -> dict[str, float]:
    q = {
        "measures": ["sales.revenue", "sales.quantity", "sales.orders_count"],
        "dimensions": ["sales.customer_region"],
    }
    rows = rest_load(base, token, q)
    return {r["sales.customer_region"]: float(r["sales.revenue"]) for r in rows}


def test_load_admin_all_regions(cube_up, CUBE_URL, admin_jwt):
    regions = _revenue_by_region(CUBE_URL, admin_jwt)
    assert set(regions) == REGIONS


def test_load_user_single_region_matches_admin(cube_up, CUBE_URL, admin_jwt, user_jwt, user_region):
    admin_rows, user_rows = (
        _revenue_by_region(CUBE_URL, admin_jwt),
        _revenue_by_region(CUBE_URL, user_jwt),
    )
    assert set(user_rows) == {user_region}
    assert user_rows[user_region] == pytest.approx(admin_rows[user_region], rel=1e-9)


def test_load_user_matches_reference(cube_up, CUBE_URL, user_jwt, user_region, duckdb_con):
    """Ground truth sf-независимо: тот же регион, посчитанный напрямую в DuckDB."""
    ref = duckdb_con.execute(
        "SELECT SUM(f.net_price) FROM pocketstack.marts.fact_sales f "
        "JOIN pocketstack.marts.dim_customer c ON f.customer_id = c.customer_id "
        f"WHERE c.customer_region = '{user_region}'"
    ).fetchone()[0]
    got = _revenue_by_region(CUBE_URL, user_jwt)[user_region]
    assert got == pytest.approx(float(ref), rel=1e-9)


def test_load_user_forbidden_measure_denied(cube_up, CUBE_URL, user_jwt):
    q = {"measures": ["sales.avg_discount"], "dimensions": ["sales.customer_region"]}
    with pytest.raises(CubeRestError):
        rest_load(CUBE_URL, user_jwt, q)


def test_load_user_row_filter_in_sql(cube_up, CUBE_URL, user_jwt, user_region):
    """Ground truth: row_level-фильтр вшит в SQL КОМПИЛЯЦИИ (/v1/sql, без кэша).

    Куб не может исполнить запрос user'а без регионального WHERE: фильтр
    добавляется на этапе компиляции, до любого исполнения/кэша.
    """
    q = {"measures": ["sales.revenue"], "dimensions": ["sales.market_segment"]}
    r = requests.post(
        f"{CUBE_URL}/cubejs-api/v1/sql",
        json={"query": q},
        headers={"Authorization": user_jwt},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    payload = r.json()
    sql_text, params = payload["sql"]["sql"]
    assert "customer_region" in sql_text, "в SQL нет вшитого фильтра по региону"
    assert user_region in params, f"в параметрах SQL нет региона {user_region}: {params}"


def test_load_user_row_filter_in_query_log(cube_up, sqlapi_user_conn, query_log_path):
    """Ground truth-исполнение: фильтр виден в DuckDB query log.

    Кэш Cube нормализует запросы (LIMIT/комментарии не меняют cache key),
    поэтому роутим семантику: случайные (год, месяц) из 84 комбинаций —
    пока не найдётся холодный вариант и SQL реально исполнится.
    """
    from harness.clients import sqlapi_query

    combos = random.sample([(y, m) for y in range(1992, 1999) for m in range(1, 13)], 8)
    for year, month in combos:
        marker = datetime.now(UTC).isoformat(timespec="milliseconds")
        sqlapi_query(
            sqlapi_user_conn,
            "SELECT sales.market_segment, SUM(sales.revenue) FROM sales "
            f"WHERE sales.year = {year} AND sales.month = {month} GROUP BY 1",
        )
        lines = query_log_path.read_text(encoding="utf-8").splitlines()
        fresh = [ln for ln in lines if ",OK," in ln and ln[: len(marker)] >= marker]
        if any("customer_region" in ln and "market_segment" in ln for ln in fresh):
            return  # фильтр зафиксирован в исполнённом SQL
    pytest.fail("ни одна комбинация год×месяц не исполнилась свежо (всё из кэша?)")


# --- 3. SQL API :15432: per-role sqlUser --------------------------------------


def test_sqlapi_admin_all_regions(cube_up, sqlapi_conn):
    from harness.clients import sqlapi_query

    rows = sqlapi_query(sqlapi_conn, SQLAPI_REGION_QUERY)
    assert {r[0] for r in rows} == REGIONS


def test_sqlapi_user_region_only(cube_up, sqlapi_conn, sqlapi_user_conn, user_region):
    from harness.clients import sqlapi_query

    admin_rows = dict(sqlapi_query(sqlapi_conn, SQLAPI_REGION_QUERY))
    user_rows = sqlapi_query(sqlapi_user_conn, SQLAPI_REGION_QUERY)
    assert len(user_rows) == 1 and user_rows[0][0] == user_region
    assert float(user_rows[0][1]) == pytest.approx(float(admin_rows[user_region]), rel=1e-9)


def test_sqlapi_user_forbidden_member_denied(cube_up, sqlapi_conn, sqlapi_user_conn):
    """Контраст: admin считает avg_discount, user получает ошибку доступа."""
    from harness.clients import sqlapi_query

    sqlapi_query(sqlapi_conn, SQLAPI_FORBIDDEN)  # admin: ок
    with pytest.raises(psycopg.errors.Error):
        sqlapi_query(sqlapi_user_conn, SQLAPI_FORBIDDEN)


def test_sqlapi_bad_password_rejected(cube_up):
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(
            host=os.environ.get("CUBESQL_HOST", "localhost"),
            port=int(os.environ.get("CUBESQL_PORT", "15432")),
            user=required("CUBESQL_USER"),
            password="definitely-wrong-password",
            dbname="default",
        )


# --- 4. MCP-клиент под ролью (обязательный инструмент демо) -------------------


@pytest.fixture()
def mcp_as_role(cube_up):
    """Перезагрузить cube_mcp.client с env выбранной роли; после теста — откат.

    MCP-сервер не хардкодит роль: REST-токен приходит через CUBEJS_API_TOKEN
    (готовый JWT любой роли), креды SQL API — через CUBESQL_*. «Агент под
    ролью user» = тот же код с user-JWT и учёткой CUBESQL_RBAC_USER.
    """
    import cube_mcp.client as mcp_client

    keys = ("CUBEJS_API_TOKEN", "CUBESQL_USER", "CUBESQL_PASSWORD")
    saved = {k: os.environ.get(k) for k in keys}

    def use(token: str, sql_user: str, sql_password: str):
        os.environ["CUBEJS_API_TOKEN"] = token
        os.environ["CUBESQL_USER"] = sql_user
        os.environ["CUBESQL_PASSWORD"] = sql_password
        return importlib.reload(mcp_client)

    yield use
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(mcp_client)


def test_mcp_user_role(mcp_as_role, user_jwt, user_region):
    """Агент MCP с токеном user: 3 меры в meta, один регион в load."""
    mcp = mcp_as_role(user_jwt, required("CUBESQL_RBAC_USER"), required("CUBESQL_RBAC_PASSWORD"))
    meta = json.loads(mcp.cube_meta())
    sales = next(c for c in meta["cubes"] if c["name"] == "sales")
    assert {m["name"] for m in sales.get("measures", [])} == USER_MEASURES

    out = json.loads(mcp.cube_load(["sales.revenue"], ["sales.customer_region"]))
    assert out["row_count"] == 1 and out["rows"][0]["sales.customer_region"] == user_region


def test_mcp_admin_role(mcp_as_role, CUBE_TOKEN):
    mcp = mcp_as_role(CUBE_TOKEN, required("CUBESQL_USER"), required("CUBESQL_PASSWORD"))
    meta = json.loads(mcp.cube_meta())
    sales = next(c for c in meta["cubes"] if c["name"] == "sales")
    assert {m["name"] for m in sales.get("measures", [])} == ALL_MEASURES


# --- 5. токены: подпись --------------------------------------------------------


def test_token_signature_roundtrip():
    claims = {"groups": ["user"], "region": "ASIA"}
    token = mint_cube_token("s3cret", claims, ttl_seconds=60)
    assert verify_cube_token("s3cret", token)["groups"] == ["user"]
    with pytest.raises(ValueError):
        verify_cube_token("other-secret", token)
