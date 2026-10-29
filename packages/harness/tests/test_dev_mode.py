"""Dev-режим (Playground): запрос без токена получает admin-доступ.

Вопреки ранней заметке в gotchas, access_policy применяется и в dev-режиме:
Playground ходит без Authorization → securityContext пуст → групп нет →
deny by default (WHERE 1=0). Фикс — dev-фолбэк в contextToGroups (cube.js):
безтокенный запрос в dev = группа admin. Проверяем через REST /v1/load.
"""


import pytest
import requests
from conftest import CUBE_URL_VALUE


@pytest.fixture(autouse=True, scope="session")
def require_dev_mode(cube_up):
    """Тест имеет смысл только в dev-режиме: в проду безтокенный запрос → 403."""
    r = requests.get(
        f"{CUBE_URL_VALUE}/cubejs-api/v1/meta",
        timeout=30,
    )
    if r.status_code == 403:
        pytest.skip("Cube в прод-режиме (безтокенный запрос корректно отклонён)")
    if r.status_code != 200:
        pytest.skip(f"Cube ответил /meta HTTP {r.status_code} без токена — неожиданно")


def test_dev_tokenless_load_gets_admin(cube_up):
    """Playground-запрос (без Authorization) не должен получать WHERE 1=0."""
    r = requests.post(
        f"{CUBE_URL_VALUE}/cubejs-api/v1/load",
        json={"query": {"measures": ["sales.revenue"]}},
        timeout=60,
    )
    assert r.status_code == 200, f"/load HTTP {r.status_code}: {r.text[:300]}"
    data = r.json().get("data")
    assert data, "dev-режим: запрос без токена вернул пустой результат (deny by default?)"
    assert data[0].get("sales.revenue"), f"выручка пуста: {data}"
