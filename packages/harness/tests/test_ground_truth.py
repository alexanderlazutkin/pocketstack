"""(c) Ground truth: реальные запросы Cube к DuckDB (log_query_path) == /v1/sql.

Требует запуска `just cube` с CUBEJS_DUCKDB_QUERY_LOG (Justfile ставит её сам).
Кубе-кэш обходим через renewQuery: true — иначе запрос к БД не повторится.

Лог DuckDB пишет один запрос многими строками (переводы строк внутри SQL),
поэтому сравниваем нормализованный текст файла целиком, а не построчно.
"""

import pytest

from harness.clients import rest_load, rest_sql
from harness.golden import GOLDEN
from harness.normalize import norm_sql


@pytest.mark.parametrize("g", GOLDEN, ids=[g["id"] for g in GOLDEN])
def test_ground_truth(g, cube_up, query_log_path, results, CUBE_URL, CUBE_TOKEN):
    expected = norm_sql(rest_sql(CUBE_URL, CUBE_TOKEN, g["rest"]))
    rest_load(CUBE_URL, CUBE_TOKEN, g["rest"], renew=True)

    blob = norm_sql(query_log_path.read_text(encoding="utf-8", errors="replace"))
    assert expected in blob, (
        f"SQL из /v1/sql не найден в логе DuckDB {query_log_path}:\n{expected[:200]}"
    )
    results["ground_truth"][g["id"]] = True
