"""Тесты нативного TPC-H бенчмарка №16 (docs/plan.md §9): file vs ducklake.

Юнит — чистые помощники (сравнение/парсинг/отчёт в формате ducklake-sandbox
+ блок параметров прогона); интеграция — файловый dbgen-таргет на sf=0.01
(dbgen ~0.1 c) + валидация tpch_answers(); lake-часть — под RUN_LAKE_TESTS=1.
"""

import os

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

LAKE_TESTS = os.environ.get("RUN_LAKE_TESTS", "") == "1"


# ---------------------------------------------------------------- helpers ----
def _tpch_con():
    con = duckdb.connect()
    con.execute("INSTALL tpch")
    con.execute("LOAD tpch")
    return con


def _bench_fixture():
    """bench_summary: long-формат (query × target), как benchmark_summary.csv."""
    return [
        {
            "query": "Q01",
            "target": "file",
            "iterations": 3,
            "avg_time_ms": 120.0,
            "min_time_ms": 110.0,
            "max_time_ms": 130.0,
            "p50_time_ms": 120.0,
            "total_time_ms": 360.0,
            "rows": 4,
            "status": "success",
        },
        {
            "query": "Q02",
            "target": "file",
            "iterations": 3,
            "avg_time_ms": 80.0,
            "min_time_ms": 70.0,
            "max_time_ms": 90.0,
            "p50_time_ms": 80.0,
            "total_time_ms": 240.0,
            "rows": 140,
            "status": "success",
        },
        {
            "query": "Q01",
            "target": "ducklake",
            "iterations": 3,
            "avg_time_ms": 300.0,
            "min_time_ms": 290.0,
            "max_time_ms": 310.0,
            "p50_time_ms": 300.0,
            "total_time_ms": 900.0,
            "rows": 4,
            "status": "success",
        },
        {
            "query": "Q02",
            "target": "ducklake",
            "iterations": 3,
            "avg_time_ms": 150.0,
            "min_time_ms": 140.0,
            "max_time_ms": 160.0,
            "p50_time_ms": 150.0,
            "total_time_ms": 450.0,
            "rows": 140,
            "status": "success",
        },
    ]


def _validation_fixture():
    return [
        {
            "query": "Q01",
            "parity": "OK",
            "parity_reason": "",
            "answers": "OK",
            "answers_reason": "",
        },
        {
            "query": "Q02",
            "parity": "OK",
            "parity_reason": "",
            "answers": "n/a",
            "answers_reason": "нет эталона tpch_answers() для sf=10",
        },
    ]


def _meta_fixture():
    return {
        "run": "2026-10-31T120000",
        "commit": "abc1234",
        "sf": "1",
        "n": 3,
        "target": "file + ducklake",
        "queries": "Q1–Q22 (22)",
        "answers": "вкл (sf=1)",
        "duckdb": "1.5.5",
    }


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


def test_stats_median_min_avg_max():
    s = stats([100.0, 50.0, 200.0])
    assert s["p50"] == pytest.approx(100.0)
    assert s["min"] == pytest.approx(50.0)
    assert s["max"] == pytest.approx(200.0)
    assert s["avg"] == pytest.approx(116.6666667)


# ------------------------------------------------------------------ отчёт ----
def test_build_summary_md_params_block():
    md = build_summary_md(_bench_fixture(), _validation_fixture(), _meta_fixture())
    assert "## Параметры прогона" in md
    params_block = md.split("## Параметры прогона", 1)[1][:1200]
    for value in (
        "2026-10-31T120000",
        "`abc1234`",
        "| 1 |",
        "| 3 |",
        "file + ducklake",
        "Q1–Q22 (22)",
        "1.5.5",
    ):
        assert value in params_block, value


def test_build_summary_md_table_and_totals():
    md = build_summary_md(_bench_fixture(), _validation_fixture(), _meta_fixture())
    for frag in (
        "| Q | rows |",
        "parity",
        "answers",
        "file p50 (min), мс",
        "ducklake p50 (min), мс",
        "| Q01 | 4 |",
        "| Q02 | 140 |",
    ):
        assert frag in md, frag
    assert "Σp50" in md and "медиана" in md and "Σavg" in md
    assert "200" in md  # Σp50 file = 120+80
    assert "450" in md  # Σp50 ducklake = 300+150
    assert "100.0" in md  # медиана p50 file
    assert "225.0" in md  # медиана p50 ducklake
    assert "parity 2/2" in md
    assert "answers 1/2" in md  # n/a не считается OK


def test_build_summary_md_single_target():
    bench = [r for r in _bench_fixture() if r["target"] == "file"]
    validation = [dict(v, parity="—") for v in _validation_fixture()]
    md = build_summary_md(bench, validation, {**_meta_fixture(), "target": "file"})
    assert "| Q01 | 4 |" in md
    assert "—" in md  # ducklake-колонки пустые
    assert "ducklake 0" not in md  # одиночная цель не даёт фиктивных нулей
    assert "; parity —" in md and "; answers 1/2." in md


def test_write_run_artifacts_sandbox_format(tmp_path):
    detail = [
        {
            "query": "Q01",
            "target": "file",
            "attempt": 1,
            "time_ms": 10.5,
            "rows": 4,
            "status": "success",
        },
        {
            "query": "Q01",
            "target": "ducklake",
            "attempt": 1,
            "time_ms": 20.5,
            "rows": 4,
            "status": "success",
        },
    ]
    queries = {1: "SELECT 1"}
    write_run(detail, _bench_fixture(), _validation_fixture(), queries, tmp_path, _meta_fixture())
    d = (tmp_path / "benchmark_detailed_timing.csv").read_text()
    assert d.splitlines()[0] == "query,target,attempt,time_ms,rows,status"
    assert "Q01" in d
    s = (tmp_path / "benchmark_summary.csv").read_text()
    assert s.splitlines()[0] == (
        "query,target,iterations,avg_time_ms,min_time_ms,max_time_ms,p50_time_ms,total_time_ms,rows,status"
    )
    v = (tmp_path / "validation_summary.csv").read_text()
    assert v.splitlines()[0] == "query,parity,parity_reason,answers,answers_reason"
    q = (tmp_path / "tpch_all_queries.sql").read_text()
    assert "Scale Factor: 1" in q and "-- Query 1" in q
    assert (tmp_path / "summary.md").exists()


def test_append_index_header_once_with_params(tmp_path):
    idx = tmp_path / "index.md"
    meta = {**_meta_fixture(), "n": 3, "target": "file + ducklake"}
    append_index(idx, meta, _bench_fixture(), _validation_fixture())
    append_index(idx, {**meta, "run": "r2"}, _bench_fixture(), _validation_fixture())
    text = idx.read_text()
    assert text.count("| run | commit |") == 1
    assert "| N |" in text and "| target |" in text
    assert "| 2026-10-31T120000 |" in text and "| r2 |" in text
    assert "| 3 |" in text  # N
    assert "| 200 |" in text and "| 450 |" in text  # Σp50 file/ducklake


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
        detail, bench, validation = run_benchmark(
            {"file": file_con}, queries=get_queries(tpch, [1, 22]), n=1, sf=0.01, answers_con=tpch
        )
    finally:
        file_con.close()
        tpch.close()
    assert len(detail) == 2  # 2 запроса × 1 цель × 1 итерация
    assert all(r["status"] == "success" for r in detail)
    assert {r["target"] for r in bench} == {"file"}
    assert all(r["status"] == "success" for r in bench)
    assert len(validation) == 2
    assert all(v["parity"] == "—" for v in validation)  # одна цель — паритета нет
    assert all(v["answers"] == "OK" for v in validation)  # ответы есть для sf=0.01


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
        detail, bench, validation = run_benchmark(
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
    assert validation[0]["parity"] == "OK"
    assert validation[0]["answers"] == "OK"
    assert {r["target"] for r in bench} == {"file", "ducklake"}
    assert len(detail) == 2

    # зачистка тестовой схемы
    from seed_tpch import lake_attach

    con = duckdb.connect()
    try:
        lake_attach(con, alias="pocketstack")
        con.execute("DROP SCHEMA IF EXISTS pocketstack.tpch_native_test CASCADE")
    finally:
        con.close()
