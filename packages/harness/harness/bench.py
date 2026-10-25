"""Лог оценки golden-вопросов: производительность + паритет, каталог results/.

Протокол: docs/bench-protocol.md. Запуск: `just bench` (требует `just cube`).

Каталог results/ (в git — история прогонов):
    results/queries/<id>.sql   — SQL, сгенерированный Cube (/v1/sql), детерминирован
    results/runs/<ts>/detail.csv   — детально: вопрос × путь × итерация → мс, rows
    results/runs/<ts>/summary.csv  — сводно: вопрос → p50/min по путям, parity, хэш
    results/runs/<ts>/summary.md   — то же таблицей для чтения
    results/index.md           — журнал прогонов: run, commit, итоги

Пути: REST (/v1/load, renewQuery=true — кэш Cube отключён),
SQL API (pg-wire :15432), REF (эталонный SQL к DuckDB marts).
"""

import csv
import datetime
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import psycopg
import requests

from .clients import reference_query, rest_load, rest_sql, sqlapi_query
from .golden import GOLDEN
from .normalize import hash_sql, norm_rows

N_RUNS = 3
DETAIL_COLUMNS = ["question_id", "path", "iteration", "ms", "rows"]
SUMMARY_CSV_COLUMNS = [
    "id",
    "rows",
    "parity",
    "rest_p50_ms",
    "rest_min_ms",
    "sqlapi_p50_ms",
    "sqlapi_min_ms",
    "ref_p50_ms",
    "ref_min_ms",
    "sql_hash",
]


def _timed_ms(fn, *args, **kwargs) -> float:
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0


def _stats(times: list[float]) -> tuple[float, float]:
    return statistics.median(times), min(times)


def _git(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return "n/a"


def _parity(g, rest_rows, api_rows, ref_rows) -> str:
    """Канонизированное сравнение строк трёх путей (как в verify, компактно)."""
    k = g["key_cols"]
    a, b, c = (norm_rows(rest_rows, k), norm_rows(api_rows, k), norm_rows(ref_rows, k))
    if not g.get("ordered"):
        a, b, c = sorted(a), sorted(b), sorted(c)
    return "OK" if a == b == c else "FAIL"


def bench_question(g, base, token, sqlapi_conn, duckdb_con, qdir, n_runs):
    """Один вопрос: SQL-файл, тайминги по итерациям, паритет. → (summary, detail)."""
    sql = rest_sql(base, token, g["rest"])
    (qdir / f"{g['id']}.sql").write_text(sql, encoding="utf-8")

    detail, times = [], {"rest": [], "sqlapi": [], "ref": []}
    rest_rows = api_rows = ref_rows = None
    for i in range(1, n_runs + 1):
        ms = _timed_ms(rest_load, base, token, g["rest"], True)
        times["rest"].append(ms)
        detail.append(
            {
                "question_id": g["id"],
                "path": "rest",
                "iteration": i,
                "ms": round(ms, 2),
                "rows": None,
            }
        )
        ms = _timed_ms(sqlapi_query, sqlapi_conn, g["sqlapi"])
        times["sqlapi"].append(ms)
        detail.append(
            {
                "question_id": g["id"],
                "path": "sqlapi",
                "iteration": i,
                "ms": round(ms, 2),
                "rows": None,
            }
        )
        ms = _timed_ms(reference_query, duckdb_con, g["reference"])
        times["ref"].append(ms)
        detail.append(
            {
                "question_id": g["id"],
                "path": "ref",
                "iteration": i,
                "ms": round(ms, 2),
                "rows": None,
            }
        )

    # rows для паритета и rowcount — по одному свежему прогону каждого пути
    from .clients import rows_rest

    rest_rows = rows_rest(rest_load(base, token, g["rest"], True), g["rest"])
    api_rows = sqlapi_query(sqlapi_conn, g["sqlapi"])
    ref_rows = reference_query(duckdb_con, g["reference"])

    rest_p50, rest_min = _stats(times["rest"])
    api_p50, api_min = _stats(times["sqlapi"])
    ref_p50, ref_min = _stats(times["ref"])
    summary = {
        "id": g["id"],
        "question": g["question"],
        "rows": len(ref_rows),
        "parity": _parity(g, rest_rows, api_rows, ref_rows),
        "rest_p50_ms": rest_p50,
        "rest_min_ms": rest_min,
        "sqlapi_p50_ms": api_p50,
        "sqlapi_min_ms": api_min,
        "ref_p50_ms": ref_p50,
        "ref_min_ms": ref_min,
        "sql_hash": hash_sql(sql),
    }
    return summary, detail


def write_run(detail, summary, run_dir: Path, meta: dict) -> None:
    """detail.csv + summary.csv + summary.md одного прогона."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "detail.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DETAIL_COLUMNS)
        w.writeheader()
        w.writerows(detail)
    with (run_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_CSV_COLUMNS)
        w.writeheader()
        for r in summary:
            w.writerow(
                {
                    k: (f"{r[k]:.1f}" if isinstance(r[k], float) else r[k])
                    for k in SUMMARY_CSV_COLUMNS
                }
            )

    lines = [
        f"# Оценка: {meta.get('run', '—')}",
        "",
        f"_commit `{meta['commit']}`, N={meta['n_runs']} итераций на путь_",
        "",
        "REST — `/v1/load` c `renewQuery` (кэш Cube отключён); "
        "SQL API — pg-wire `:15432`; REF — эталонный SQL к DuckDB.",
        "",
        "| Вопрос | rows | parity | REST p50 (min), мс | SQL API p50 (min), мс "
        "| REF p50 (min), мс | SQL-хэш | файл |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in summary:
        lines.append(
            f"| `{r['id']}` | {r['rows']} | {r['parity']} "
            f"| {r['rest_p50_ms']:.0f} ({r['rest_min_ms']:.0f}) "
            f"| {r['sqlapi_p50_ms']:.0f} ({r['sqlapi_min_ms']:.0f}) "
            f"| {r['ref_p50_ms']:.0f} ({r['ref_min_ms']:.0f}) "
            f"| `{r['sql_hash'][:12]}` | [SQL](../queries/{r['id']}.sql) |"
        )
    ok = sum(1 for r in summary if r["parity"] == "OK")
    lines += ["", f"**Итог**: {len(summary)} вопросов, паритет {ok}/{len(summary)}.", ""]
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def append_index(index: Path, meta: dict, summary: list[dict]) -> None:
    """results/index.md — журнал прогонов (шапка при первом создании)."""
    header = "| run | commit | вопросов | parity | REST Σp50, мс | SQL API Σp50, мс | REF Σp50, мс |\n|---|---|---|---|---|---|---|"
    row = (
        f"| {meta['run']} | `{meta['commit']}` | {len(summary)} "
        f"| {sum(1 for r in summary if r['parity'] == 'OK')}/{len(summary)} "
        f"| {sum(r['rest_p50_ms'] for r in summary):.0f} "
        f"| {sum(r['sqlapi_p50_ms'] for r in summary):.0f} "
        f"| {sum(r['ref_p50_ms'] for r in summary):.0f} |"
    )
    existing = index.read_text(encoding="utf-8") if index.exists() else ""
    if "| run | commit |" in existing:
        updated = existing.rstrip("\n") + "\n" + row + "\n"
    else:
        updated = "# Журнал оценок (results/runs/*)\n\n" + header + "\n" + row + "\n"
    index.write_text(updated, encoding="utf-8")


def main() -> int:
    base = os.environ.get("CUBEJS_URL", "http://localhost:4000")
    token = os.environ.get("CUBEJS_API_SECRET", "pocketstack-demo-secret")
    here = Path(__file__).resolve().parent.parent  # packages/harness
    repo = here.parent.parent
    results_root = repo / "results"

    try:
        requests.get(f"{base}/cubejs-api/v1/meta", timeout=3)
    except requests.RequestException:
        print(f"Cube недоступен на {base}: запустите `just cube`", file=sys.stderr)
        return 2

    sqlapi_conn = psycopg.connect(
        host=os.environ.get("CUBESQL_HOST", "localhost"),
        port=int(os.environ.get("CUBESQL_PORT", "15432")),
        user=os.environ.get("CUBESQL_USER", "sql-user"),
        password=os.environ.get("CUBESQL_PASSWORD", "sql-password"),
        dbname="default",
    )
    duckdb_con = duckdb.connect(str(repo / "warehouse" / "pocketstack.duckdb"), read_only=True)

    run_id = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    run_dir = results_root / "runs" / run_id
    qdir = results_root / "queries"
    qdir.mkdir(parents=True, exist_ok=True)

    try:
        summaries, details = [], []
        for g in GOLDEN:
            s, d = bench_question(g, base, token, sqlapi_conn, duckdb_con, qdir, N_RUNS)
            summaries.append(s)
            details.extend(d)
        meta = {"run": run_id, "commit": _git(repo), "n_runs": N_RUNS}
        write_run(details, summaries, run_dir, meta)
        append_index(results_root / "index.md", meta, summaries)
    finally:
        sqlapi_conn.close()
        duckdb_con.close()

    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"Прогон: {run_dir}\nЖурнал: {results_root / 'index.md'}")
    return 0 if all(s["parity"] == "OK" for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
