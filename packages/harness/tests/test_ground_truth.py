"""(c) Ground truth: реальные запросы Cube к DuckDB (log_query_path) == /v1/sql.

Требует запуска `just cube` (CUBEJS_DUCKDB_QUERY_LOG, Justfile ставит её сам).
Кубе-кэш обходим через renewQuery: true — иначе запрос к БД не повторится.

Формат лога (драйвер-обёртка в cube.js): одна строка на запрос
    started_at,finished_at,duration_ms,status,sql
(sql схлопнут в одну строку; статус OK/ERR). Совместимость со старым форматом
(голый SQL многими строками) — blob-проверка ниже, тайминги — только новая строка.
"""

import re

import pytest
from harness.clients import rest_load, rest_sql
from harness.golden import GOLDEN
from harness.normalize import norm_sql

_TIMING_RE = re.compile(r"^(\S+),(\S+),(\d+),(OK|ERR),")


@pytest.mark.parametrize("g", GOLDEN, ids=[g["id"] for g in GOLDEN])
def test_ground_truth(g, cube_up, query_log_path, results, CUBE_URL, CUBE_TOKEN):
    expected = norm_sql(rest_sql(CUBE_URL, CUBE_TOKEN, g["rest"]))
    rest_load(CUBE_URL, CUBE_TOKEN, g["rest"], renew=True)

    raw = query_log_path.read_text(encoding="utf-8", errors="replace")
    lines = [norm_sql(ln) for ln in raw.splitlines()]
    blob = " ".join(lines)
    assert expected in blob, (
        f"SQL из /v1/sql не найден в логе DuckDB {query_log_path}:\n{expected[:200]}"
    )

    timing_line = next((ln for ln in lines if expected in ln), None)
    assert timing_line is not None, (
        "SQL найден, но без строки таймингов (старый формат лога?) — перезапустите куб: scripts/stack.sh restart"
    )
    m = _TIMING_RE.match(timing_line)
    assert m, f"строка лога без полей времени/длительности: {timing_line[:120]}"
    assert int(m.group(3)) >= 0, f"duration_ms не число ≥ 0: {timing_line[:120]}"

    results["ground_truth"][g["id"]] = True
