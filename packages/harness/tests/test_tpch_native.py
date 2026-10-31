"""Тесты нативного TPC-H бенчмарка №16 (docs/plan.md §9): file vs ducklake.

Юнит — чистые помощники (сравнение/парсинг/отчёт); интеграция — файловый
dbgen-таргет на sf=0.01 (dbgen ~0.1 c) + валидация tpch_answers();
lake-часть — под RUN_LAKE_TESTS=1 (как test_lake_* в pocketstack-sqlmesh).
"""

import os
from pathlib import Path

import duckdb
import pytest
from harness.tpch_native import (
    answer_matches,
    append_index,
    bootstrap,
    build_summary_md,
    compare_results,
    get_answer,
    get_queries,
    open_file_target,
    parse_answer,
    run_benchmark,
    sf_key,
    stats,
    write_run,
)

HERE = Path(__file__).resolve().parent
LAKE_TESTS = os.environ.get("RUN_LAKE_TESTS", "") == "1"


# ---------------------------------------------------------------- helpers ----
def _tpch_con():
    con = duckdb.connect()
    con.execute("INSTALL tpch")
    con.execute("LOAD tpch")
    return con


# ------------------------------------------------------------ чистые юниты ----
def test_sf_key():
    assert sf_key(1) == "1"
    assert sf_key(10.0) == "10"
    assert sf_key(0.01) == "0.01"
    assert sf_key(0.1) == "0.1"


def test_compare_results_tolerant_and_order_insensitive():
    a = [("A", 1.0000001, 3), ("B", 2.5, 4)]
    b = [("B", 2.5, 4), ("A", 1.0, 3)]  # другой порядок строк + допуск float
    ok, reason = compare_results(a, b)
    assert ok, reason

    c = [("A", 1.6, 3), ("B", 2.5, 4)]
    ok, _ = compare_results(a, c)
    assert not ok


def test_compare_results_detects_shape_and_string_mismatch():
    assert not compare_results([("A", 1)], [("A", 1), ("B", 2)])[0]  # длина
    assert not compare_results([("A", 1)], [("C", 1)])[0]  # строка


def test_parse_answer():
    text = "l_returnflag|sum_qty\nA|100\nB|200.50\n"
    header, rows = parse_answer(text)
    assert header == ["l_returnflag", "sum_qty"]
    assert rows == [("A", "100"), ("B", "200.50")]


def test_answer_matches_rounds_to_answer_precision():
    # avg в ответах TPC-H округлены до 2 знаков; наш результат — полный
    ours = [("A", 25.3578972, 37734107)]
    answer = "flag|avg_q|cnt\nA|25.36|37734107\n"
    ok, reason = answer_matches(ours, answer)
    assert ok, reason

    bad = [("A", 25.9, 37734107)]
    ok, _ = answer_matches(bad, answer)
    assert not ok


def test_answer_matches_string_columns_and_count():
    ours = [("AMERICA", 2), ("EUROPE", 1)]
    answer = "region|n\nAMERICA|2\nEUROPE|1\n"
    assert answer_matches(ours, answer)[0]
    answer_bad = "region|n\nASIA|2\nEUROPE|1\n"
    assert not answer_matches(ours, answer_bad)[0]


def test_stats_median_and_min():
    s = stats([100.0, 50.0, 200.0])
    assert s["p50"] == pytest.approx(100.0)
    assert s["min"] == pytest.approx(50.0)


# ------------------------------------------------------------------ отчёт ----
def _summary_fixture():
    return [
        {
            "q": 1,
            "rows": 4,
            "parity": "OK",
            "answers": "OK",
            "file_p50_ms": 120.0,
            "file_min_ms": 110.0,
            "lake_p50_ms": 300.0,
            "lake_min_ms": 290.0,
        },
        {
            "q": 2,
            "rows": 140,
            "parity": "OK",
            "answers": "OK",
            "file_p50_ms": 80.0,
            "file_min_ms": 70.0,
            "lake_p50_ms": 150.0,
            "lake_min_ms": 140.0,
        },
    ]


def test_build_summary_md_table_and_totals():
    md = build_summary_md(_summary_fixture(), meta={"commit": "abc", "sf": "1", "n": 3})
    for frag in (
        "| Q | rows |",
        "parity",
        "answers",
        "file p50",
        "ducklake p50",
        "| 1 | 4 |",
        "| 2 | 140 |",
    ):
        assert frag in md, frag
    assert "Σp50" in md and "медиана" in md
    # Σ и медиана по обеим целям
    assert "200" in md  # Σ file = 120+80
    assert "450" in md  # Σ lake = 300+150
    assert "100.0" in md  # медиана file
    assert "225.0" in md  # медиана lake
    assert "2/2" in md  # parity и answers счётчики
    assert "`abc`" in md


def test_write_run_artifacts(tmp_path):
    detail = [
        {"q": 1, "target": "file", "iteration": 1, "ms": 10.5, "rows": 4},
        {"q": 1, "target": "ducklake", "iteration": 1, "ms": 20.5, "rows": 4},
    ]
    queries = {1: "SELECT 1"}
    write_run(
        detail, _summary_fixture(), queries, tmp_path, meta={"commit": "abc", "sf": "1", "n": 1}
    )
    assert (tmp_path / "detail.csv").read_text().splitlines()[0] == "q,target,iteration,ms,rows"
    assert (tmp_path / "summary.csv").exists()
    assert "-- Q1" in (tmp_path / "tpch_queries.sql").read_text()
    assert (tmp_path / "summary.md").exists()


def test_append_index_header_once(tmp_path):
    idx = tmp_path / "index.md"
    append_index(idx, {"run": "r1", "commit": "a", "sf": "1"}, _summary_fixture())
    append_index(idx, {"run": "r2", "commit": "b", "sf": "1"}, _summary_fixture())
    text = idx.read_text()
    assert text.count("| run | commit |") == 1
    assert "| r1 |" in text and "| r2 |" in text


# ------------------------------------------------------------ интеграция ----
def test_get_queries_and_answer_tpch_extension():
    con = _tpch_con()
    queries = get_queries(con, [1, 22])
    assert set(queries) == {1, 22}
    assert "l_returnflag" in queries[1]
    answer = get_answer(con, 1, 0.01)
    assert answer and answer.startswith("l_returnflag")


def test_bootstrap_file_and_run_smoke(tmp_path):
    """sf=0.01: dbgen ~0.1 c; file-таргет + Q1/Q22 + валидация ответов."""
    bootstrap(tmp_path, sf=0.01, lake=False)
    dbfile = tmp_path / "warehouse" / "tpch_native_sf0.01.duckdb"
    assert dbfile.exists()

    con = open_file_target(tmp_path, sf=0.01)
    try:
        n = con.execute("SELECT count(*) FROM lineitem").fetchone()[0]
        assert n == 60175  # эталон dbgen sf=0.01
    finally:
        con.close()

    meta = duckdb.connect(str(dbfile), read_only=True)
    assert meta.execute("SELECT value FROM tpch_native_meta WHERE key='sf'").fetchone()[0] == "0.01"
    meta.close()

    # повторный bootstrap идемпотентен (не пересоздаёт файл)
    before = dbfile.stat().st_mtime
    bootstrap(tmp_path, sf=0.01, lake=False)
    assert dbfile.stat().st_mtime == before

    # прогон двух запросов по file-таргету
    file_con = open_file_target(tmp_path, sf=0.01)
    tpch = _tpch_con()
    try:
        summary, detail = run_benchmark(
            {"file": file_con}, queries=get_queries(tpch, [1, 22]), n=1, sf=0.01, answers_con=tpch
        )
    finally:
        file_con.close()
        tpch.close()
    assert len(summary) == 2
    assert all(r["parity"] == "OK" for r in summary)  # одна цель — паритет с собой
    assert all(r["answers"] == "OK" for r in summary)  # ответы есть для sf=0.01
    assert len(detail) == 2  # 2 запроса × 1 цель × 1 итерация


@pytest.mark.skipif(not LAKE_TESTS, reason="RUN_LAKE_TESTS=1 (нужны pg+minio из docker compose)")
def test_bootstrap_lake_and_run(tmp_path):
    """sf=0.01 в выделенную схему lake (tpch_native_test), file vs ducklake."""
    bootstrap(tmp_path, sf=0.01, lake=True, schema="tpch_native_test")
    from harness.tpch_native import open_lake_target

    lake_con = open_lake_target(schema="tpch_native_test")
    file_con = open_file_target(tmp_path, sf=0.01)
    tpch = _tpch_con()
    try:
        assert lake_con.execute("SELECT count(*) FROM lineitem").fetchone()[0] == 60175
        summary, detail = run_benchmark(
            {"file": file_con, "ducklake": lake_con},
            queries=get_queries(tpch, [1]),
            n=1,
            sf=0.01,
            answers_con=tpch,
        )
    finally:
        lake_con.close()
        file_con.close()
        tpch.close()
    assert summary[0]["parity"] == "OK"
    assert summary[0]["answers"] == "OK"
    assert len(detail) == 2

    # зачистка тестовой схемы
    from seed_tpch import lake_attach

    con = duckdb.connect()
    try:
        lake_attach(con, alias="pocketstack")
        con.execute("DROP SCHEMA IF EXISTS pocketstack.tpch_native_test CASCADE")
    finally:
        con.close()
