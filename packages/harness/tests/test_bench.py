"""Юнит-тесты лога оценок в results/ (TDD, RED до новой версии harness.bench)."""

import pytest

from harness.bench import append_index, write_run


@pytest.fixture
def detail_rows():
    # итерации: вопрос × путь × N
    return [
        {"question_id": "total_revenue", "path": "rest", "iteration": 1, "ms": 5.1, "rows": 1},
        {"question_id": "total_revenue", "path": "sqlapi", "iteration": 1, "ms": 52.0, "rows": 1},
        {"question_id": "total_revenue", "path": "ref", "iteration": 1, "ms": 1.2, "rows": 1},
    ]


@pytest.fixture
def summary_rows():
    return [
        {
            "id": "total_revenue",
            "question": "Выручка?",
            "rows": 1,
            "parity": "OK",
            "rest_p50_ms": 5.1,
            "rest_min_ms": 5.1,
            "sqlapi_p50_ms": 52.0,
            "sqlapi_min_ms": 52.0,
            "ref_p50_ms": 1.2,
            "ref_min_ms": 1.2,
            "sql_hash": "a" * 64,
        }
    ]


def test_write_run_makes_detail_and_summary(tmp_path, detail_rows, summary_rows):
    run_dir = tmp_path / "runs" / "2026-10-25T210000"
    write_run(detail_rows, summary_rows, run_dir, meta={"commit": "abc1234", "n_runs": 1})
    detail, summary_csv, summary_md = (
        run_dir / "detail.csv",
        run_dir / "summary.csv",
        run_dir / "summary.md",
    )
    assert detail.exists() and summary_csv.exists() and summary_md.exists()

    dhead = detail.read_text().splitlines()[0]
    assert dhead == "question_id,path,iteration,ms,rows"

    stext = summary_csv.read_text()
    assert stext.splitlines()[0].startswith("id,rows,parity")
    assert "total_revenue" in stext

    mtext = summary_md.read_text()
    for col in ("Вопрос", "rows", "parity", "REST p50", "SQL API p50", "REF p50"):
        assert col in mtext, col
    assert "`abc1234`" in mtext  # commit в шапке


def test_summary_md_links_query_files(tmp_path, detail_rows, summary_rows):
    run_dir = tmp_path / "runs" / "x"
    write_run(detail_rows, summary_rows, run_dir, meta={"commit": "a", "n_runs": 1})
    assert "../queries/total_revenue.sql" in (run_dir / "summary.md").read_text()


def test_append_index_creates_and_appends(tmp_path, summary_rows):
    idx = tmp_path / "index.md"
    meta1 = {"run": "2026-10-25T210000", "commit": "abc1234"}
    meta2 = {"run": "2026-10-25T220000", "commit": "def5678"}
    append_index(idx, meta1, summary_rows)
    append_index(idx, meta2, summary_rows)

    text = idx.read_text()
    assert "| run | commit |" in text  # шапка создана один раз
    assert text.count("| 2026-") == 2  # две строки прогонов
    assert "abc1234" in text and "def5678" in text
