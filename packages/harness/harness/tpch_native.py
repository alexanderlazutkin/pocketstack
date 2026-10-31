"""Нативный TPC-H бенчмарк №16 (docs/plan.md §9, docs/user-guide-tpch-benchmark.md).

22 запроса TPC-H из расширения tpch (tpch_queries()) против dbgen-данных,
БЕЗ семантического слоя — чистый базлайн движка в двух физических раскладках:
- file:     отдельный dbgen-файл warehouse/tpch_native_sf<N>.duckdb (таблицы в main);
- ducklake: те же данные CTAS-ом в выделенную схему lake (pg-каталог + parquet
  в MinIO), READ_ONLY-attach — приём seed_ducklake (plan.md №16: демо-данные
  не трогаем, sf бенча независим от sf витрины).

Валидация: answers tpch_answers() (есть для sf 0.01/0.1/1) по эталонной цели
(file, при её отсутствии — ducklake); паритет file ↔ ducklake — построчно
с числовой толерантностью.

Артефакты прогона — формат ducklake-sandbox (+ цель/params-блок, в git):
results/native/<ts>/{benchmark_detailed_timing.csv, benchmark_summary.csv,
validation_summary.csv, tpch_all_queries.sql, summary.md} + журнал
results/native/index.md. Запуск: just bench-native [sf] — см. user guide.
"""

import argparse
import csv
import datetime
import math
import statistics
import subprocess
import time
from pathlib import Path

import duckdb

LAKE_ALIAS = "pocketstack"  # как в harness/warehouse.py — единое логическое имя
DETAIL_COLUMNS = ["query", "target", "attempt", "time_ms", "rows", "status"]
BENCH_SUMMARY_COLUMNS = [
    "query",
    "target",
    "iterations",
    "avg_time_ms",
    "min_time_ms",
    "max_time_ms",
    "p50_time_ms",
    "total_time_ms",
    "rows",
    "status",
]
VALIDATION_COLUMNS = ["query", "parity", "parity_reason", "answers", "answers_reason"]


# --------------------------------------------------------------- канонизация --
def _num(value):
    """Числовое представление значения или None (для строк/дат)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _canon_key(row: tuple):
    """Ключ сортировки: числа как float, прочее как str — одинаковый у наших
    результатов и распарсенных ответов, чтобы позиционное сравнение было честным."""
    return tuple(_num(v) if _num(v) is not None else str(v).strip() for v in row)


def _values_match(a, b) -> bool:
    x, y = _num(a), _num(b)
    if x is not None and y is not None:
        return math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-6)
    return str(a).strip() == str(b).strip()


def compare_results(rows_a, rows_b) -> tuple[bool, str]:
    """Канонизированное построчное сравнение двух результатов (порядок строк не важен)."""
    if len(rows_a) != len(rows_b):
        return False, f"row count {len(rows_a)} vs {len(rows_b)}"
    a, b = sorted(rows_a, key=_canon_key), sorted(rows_b, key=_canon_key)
    for ra, rb in zip(a, b):
        if len(ra) != len(rb):
            return False, "column count"
        for va, vb in zip(ra, rb):
            if not _values_match(va, vb):
                return False, f"{va!r} != {vb!r}"
    return True, ""


# --------------------------------------------------------------- tpch ext -----
def _load_tpch(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("INSTALL tpch")
    con.execute("LOAD tpch")


def get_queries(con: duckdb.DuckDBPyConnection, ids) -> dict[int, str]:
    """SQL запросов из tpch_queries(): {query_nr: sql}."""
    _load_tpch(con)
    out = {}
    for q in ids:
        row = con.execute("SELECT query FROM tpch_queries() WHERE query_nr=?", [q]).fetchone()
        if row is None:
            raise SystemExit(f"tpch_queries(): нет query_nr={q}")
        out[q] = row[0]
    return out


def get_answer(con: duckdb.DuckDBPyConnection, q: int, sf: float) -> str | None:
    """Эталонный ответ из tpch_answers() (доступны sf 0.01/0.1/1) или None."""
    row = con.execute(
        "SELECT answer FROM tpch_answers() WHERE query_nr=? AND scale_factor=?",
        [q, sf],
    ).fetchone()
    return row[0] if row else None


def parse_answer(text: str) -> tuple[list[str], list[tuple]]:
    """Ответ tpch_answers(): 'a|b|c\\n1|2|3' → (header, rows-of-strings)."""
    lines = [ln for ln in text.strip().splitlines() if ln]
    if not lines:
        return [], []
    header = lines[0].split("|")
    rows = [tuple(ln.split("|")) for ln in lines[1:]]
    return header, rows


def answer_matches(our_rows, answer_text: str) -> tuple[bool, str]:
    """Сверка нашего результата с эталоном: ответы TPC-H округлены до 2 знаков —
    числовые колонки сравниваем с допуском 0.005 (наша сторона — полная точность)."""
    header, ref_rows = parse_answer(answer_text)
    if not header:
        return False, "пустой ответ tpch_answers()"
    if len(our_rows) != len(ref_rows):
        return False, f"row count {len(our_rows)} vs {len(ref_rows)}"
    ours = sorted(our_rows, key=_canon_key)
    ref = sorted(ref_rows, key=_canon_key)
    for ra, rb in zip(ours, ref):
        if len(ra) != len(rb):
            return False, "column count"
        for va, vb in zip(ra, rb):
            x, y = _num(va), _num(vb)
            if x is not None and y is not None:
                if abs(x - y) > 0.005 + 1e-9 + abs(x) * 1e-12:
                    return False, f"{va!r} != {vb!r}"
            elif str(va).strip() != str(vb).strip():
                return False, f"{va!r} != {vb!r}"
    return True, ""


# --------------------------------------------------------------- статистика ---
def stats(times: list[float]) -> dict:
    """avg/min/max/p50/total — формат ducklake-sandbox (+медиана bench-протокола)."""
    return {
        "avg": sum(times) / len(times),
        "min": min(times),
        "max": max(times),
        "p50": statistics.median(times),
        "total": sum(times),
    }


def sf_key(sf: float) -> str:
    """Каноническая запись sf: 1 → '1', 10.0 → '10', 0.01 → '0.01'."""
    return f"{sf:g}"


# --------------------------------------------------------------- bootstrap ----
def _dbgen_file(repo: Path, sf: float) -> Path:
    return repo / "warehouse" / f"tpch_native_sf{sf_key(sf)}.duckdb"


def _file_sf(dbfile: Path) -> str | None:
    if not dbfile.exists():
        return None
    try:
        con = duckdb.connect(str(dbfile), read_only=True)
        try:
            row = con.execute("SELECT value FROM tpch_native_meta WHERE key='sf'").fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except duckdb.Error:
        return None  # битый/чужой файл — перегенерируем


def bootstrap_file(repo: Path, sf: float) -> bool:
    """dbgen(sf) в ОТДЕЛЬНЫЙ файл (таблицы в main) + маркер sf. → пересоздан ли."""
    dbfile = _dbgen_file(repo, sf)
    dbfile.parent.mkdir(parents=True, exist_ok=True)
    if _file_sf(dbfile) == sf_key(sf):
        print(f"bootstrap: dbgen-файл {dbfile.name} готов (sf={sf_key(sf)})")
        return False
    for p in (dbfile, dbfile.with_name(dbfile.name + ".wal")):
        p.unlink(missing_ok=True)
    con = duckdb.connect(str(dbfile))
    try:
        _load_tpch(con)
        con.execute(f"CALL dbgen(sf={sf})")
        con.execute("CREATE TABLE tpch_native_meta (key VARCHAR, value VARCHAR)")
        con.execute(f"INSERT INTO tpch_native_meta VALUES ('sf', '{sf_key(sf)}')")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    print(f"bootstrap: dbgen sf={sf_key(sf)} → {dbfile}")
    return True


def bootstrap_lake(repo: Path, sf: float, schema: str = "tpch_native") -> bool:
    """CTAS dbgen-файла в выделенную схему lake одной транзакцией каталога
    (приём seed_ducklake). Демо-схемы (raw_tpch, marts) не затрагиваются."""
    from seed_tpch import TABLES, lake_attach

    dbfile = _dbgen_file(repo, sf)
    con = duckdb.connect()
    try:
        lake_attach(con, alias=LAKE_ALIAS)  # read-write: создание схемы — транзакция каталога
        try:
            row = con.execute(
                f"SELECT value FROM {LAKE_ALIAS}.{schema}.tpch_native_meta WHERE key='sf'"
            ).fetchone()
            if row and row[0] == sf_key(sf):
                print(f"bootstrap: lake.{schema} готов (sf={sf_key(sf)})")
                return False
        except duckdb.Error:
            pass  # схемы/меты нет — создаём
        con.execute(f"ATTACH '{dbfile}' AS src (READ_ONLY)")
        con.execute("BEGIN")
        con.execute(f"DROP SCHEMA IF EXISTS {LAKE_ALIAS}.{schema} CASCADE")
        con.execute(f"CREATE SCHEMA {LAKE_ALIAS}.{schema}")
        for t in TABLES:
            con.execute(f"CREATE TABLE {LAKE_ALIAS}.{schema}.{t} AS SELECT * FROM src.main.{t}")
        con.execute(
            f"CREATE TABLE {LAKE_ALIAS}.{schema}.tpch_native_meta (key VARCHAR, value VARCHAR)"
        )
        con.execute(
            f"INSERT INTO {LAKE_ALIAS}.{schema}.tpch_native_meta VALUES ('sf', '{sf_key(sf)}')"
        )
        con.execute("COMMIT")
        con.execute("DETACH src")
    finally:
        con.close()
    print(f"bootstrap: lake.{schema} ← dbgen sf={sf_key(sf)} (parquet в MinIO)")
    return True


def bootstrap(repo: Path, sf: float, lake: bool = True, schema: str = "tpch_native") -> dict:
    made_file = bootstrap_file(repo, sf)
    made_lake = bootstrap_lake(repo, sf, schema=schema) if lake else False
    return {"file": _dbgen_file(repo, sf), "created_file": made_file, "created_lake": made_lake}


# --------------------------------------------------------------- таргеты ------
def open_file_target(repo: Path, sf: float) -> duckdb.DuckDBPyConnection:
    """read-only коннект к dbgen-файлу (таблицы в main — запросы без квалификации)."""
    con = duckdb.connect(str(_dbgen_file(repo, sf)), read_only=True)
    _load_tpch(con)
    return con


def open_lake_target(schema: str = "tpch_native") -> duckdb.DuckDBPyConnection:
    """:memory: + READ_ONLY attach каталога (защита от AUTOMATIC_MIGRATION) + USE схема."""
    from seed_tpch import lake_attach

    con = duckdb.connect()
    lake_attach(con, read_only=True, alias=LAKE_ALIAS)
    _load_tpch(con)
    con.execute(f"USE {LAKE_ALIAS}.{schema}")
    return con


# --------------------------------------------------------------- прогон --------
def run_benchmark(
    cons: dict[str, duckdb.DuckDBPyConnection],
    queries: dict[int, str],
    n: int,
    sf: float,
    answers_con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """N итераций каждого запроса на каждый таргет (file, затем ducklake).

    → (detail, bench_summary, validation):
    - detail: каждая попытка (формат ducklake-sandbox: query/target/attempt/time_ms/rows/status);
    - bench_summary: query × target → avg/min/max/p50/total (sandbox + p50);
    - validation: parity (file ↔ ducklake) и answers (vs tpch_answers()).
    Ошибка попытки не валит прогон: фиксируется в status (как в sandbox).
    """
    detail, bench, validation = [], [], []
    for q in sorted(queries):
        label = f"Q{q:02d}"
        sql = queries[q]
        rows_by, times_by, err_by = {}, {t: [] for t in cons}, {}
        for name, con in cons.items():  # file первым — эталон для answers
            for i in range(1, n + 1):
                t0 = time.perf_counter()
                try:
                    rows = con.execute(sql).fetchall()
                    ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    rows_by[name] = rows
                    detail.append(
                        {
                            "query": label,
                            "target": name,
                            "attempt": i,
                            "time_ms": ms,
                            "rows": len(rows),
                            "status": "success",
                        }
                    )
                    times_by[name].append(ms)
                except (
                    duckdb.Error,
                    OSError,
                    MemoryError,
                ) as e:  # фиксируем, идём дальше (как sandbox)
                    ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    err_by[name] = str(e)
                    detail.append(
                        {
                            "query": label,
                            "target": name,
                            "attempt": i,
                            "time_ms": ms,
                            "rows": 0,
                            "status": f"error: {str(e)[:80]}",
                        }
                    )
        for name in cons:
            ts = times_by[name]
            rec = {"query": label, "target": name, "iterations": len(ts), "rows": 0}
            if ts:
                s = stats(ts)
                rec.update(
                    avg_time_ms=s["avg"],
                    min_time_ms=s["min"],
                    max_time_ms=s["max"],
                    p50_time_ms=s["p50"],
                    total_time_ms=s["total"],
                    rows=len(rows_by.get(name, [])),
                    status="success",
                )
            else:
                rec.update(
                    avg_time_ms=None,
                    min_time_ms=None,
                    max_time_ms=None,
                    p50_time_ms=None,
                    total_time_ms=None,
                    status=f"error: {err_by.get(name, 'no attempts')[:80]}",
                )
            bench.append(rec)

        parity, reason = "—", ""
        if "file" in rows_by and "ducklake" in rows_by:
            ok, reason = compare_results(rows_by["file"], rows_by["ducklake"])
            parity = "OK" if ok else "FAIL"

        answers, areason = "—", ""
        ref_name = "file" if "file" in rows_by else next(iter(rows_by), None)
        if answers_con is not None and ref_name:
            answer = get_answer(answers_con, q, sf)
            if answer is None:
                answers, areason = "n/a", f"нет эталона tpch_answers() для sf={sf_key(sf)}"
            else:
                ok, areason = answer_matches(rows_by[ref_name], answer)
                answers = "OK" if ok else "FAIL"
        validation.append(
            {
                "query": label,
                "parity": parity,
                "parity_reason": reason[:120],
                "answers": answers,
                "answers_reason": areason[:120],
            }
        )
    return detail, bench, validation


# --------------------------------------------------------------- отчёт --------
def _target_stat(bench: list[dict], target: str, field: str, q: str):
    for r in bench:
        if r["query"] == q and r["target"] == target and r[field] is not None:
            return r[field]
    return None


def build_summary_md(bench: list[dict], validation: list[dict], meta: dict) -> str:
    file_p50s = [r["p50_time_ms"] for r in bench if r["target"] == "file" and r["p50_time_ms"]]
    lake_p50s = [r["p50_time_ms"] for r in bench if r["target"] == "ducklake" and r["p50_time_ms"]]
    file_avgs = [r["avg_time_ms"] for r in bench if r["target"] == "file" and r["avg_time_ms"]]
    lake_avgs = [r["avg_time_ms"] for r in bench if r["target"] == "ducklake" and r["avg_time_ms"]]
    pok = sum(1 for v in validation if v["parity"] == "OK")
    aok = sum(1 for v in validation if v["answers"] == "OK")

    lines = [
        "# Нативный TPC-H: file vs DuckLake",
        "",
        "## Параметры прогона",
        "",
        "| Параметр | Значение |",
        "|---|---|",
        f"| запуск | {meta['run']} |",
        f"| commit | `{meta['commit']}` |",
        f"| sf | {meta['sf']} |",
        f"| итераций на запрос (N) | {meta['n']} |",
        f"| цель | {meta['target']} |",
        f"| запросы | {meta['queries']} |",
        f"| answers (tpch_answers) | {meta['answers']} |",
        f"| duckdb | {meta['duckdb']} |",
        "",
        "22 запроса `tpch_queries()` к dbgen-данным без семантического слоя:",
        "file — dbgen-файл `warehouse/tpch_native_sf*.duckdb`; ducklake — та же схема",
        "в каталоге lake (pg + parquet в MinIO, READ_ONLY). Протокол: docs/bench-native-tpch.md;",
        "пошаговое воспроизведение: docs/user-guide-tpch-benchmark.md.",
        "",
        "| Q | rows | parity | answers | file p50 (min), мс | ducklake p50 (min), мс |",
        "|---|---|---|---|---|---|",
    ]
    for v in validation:
        q = v["query"]
        f50, fmin = (
            _target_stat(bench, "file", "p50_time_ms", q),
            _target_stat(bench, "file", "min_time_ms", q),
        )
        l50, lmin = (
            _target_stat(bench, "ducklake", "p50_time_ms", q),
            _target_stat(bench, "ducklake", "min_time_ms", q),
        )
        rows = next(
            (
                r["rows"]
                for r in bench
                if r["query"] == q and r["target"] == ("file" if f50 is not None else "ducklake")
            ),
            0,
        )
        f = "—" if f50 is None else f"{f50:.0f} ({fmin:.0f})"
        l = "—" if l50 is None else f"{l50:.0f} ({lmin:.0f})"
        lines.append(f"| {q} | {rows} | {v['parity']} | {v['answers']} | {f} | {l} |")

    if file_p50s and lake_p50s:
        totals = (
            f"**Итог**: Σp50 file {sum(file_p50s):.0f} / ducklake {sum(lake_p50s):.0f} мс"
            f" (Σavg {sum(file_avgs):.0f} / {sum(lake_avgs):.0f}); "
            f"медиана p50 file {statistics.median(file_p50s):.1f} / "
            f"{statistics.median(lake_p50s):.1f} мс"
        )
    elif file_p50s:
        totals = (
            f"**Итог**: Σp50 file {sum(file_p50s):.0f} мс"
            f" (Σavg {sum(file_avgs):.0f}); "
            f"медиана p50 file {statistics.median(file_p50s):.1f} мс"
        )
    elif lake_p50s:
        totals = (
            f"**Итог**: Σp50 ducklake {sum(lake_p50s):.0f} мс"
            f" (Σavg {sum(lake_avgs):.0f}); "
            f"медиана p50 ducklake {statistics.median(lake_p50s):.1f} мс"
        )
    else:
        totals = "**Итог**: успешных прогонов нет"
    p_total = sum(1 for v in validation if v["parity"] != "—")
    a_total = sum(1 for v in validation if v["answers"] != "—")
    totals += (f"; parity {pok}/{p_total}" if p_total else "; parity —") + (
        f"; answers {aok}/{a_total}." if a_total else "; answers —."
    )
    lines += ["", totals, ""]
    return "\n".join(lines)


def write_run(
    detail, bench, validation, queries: dict[int, str], run_dir: Path, meta: dict
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "benchmark_detailed_timing.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DETAIL_COLUMNS)
        w.writeheader()
        w.writerows(detail)
    with (run_dir / "benchmark_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BENCH_SUMMARY_COLUMNS)
        w.writeheader()
        for r in bench:
            w.writerow(
                {
                    k: (f"{r[k]:.2f}" if isinstance(r.get(k), float) else r.get(k))
                    for k in BENCH_SUMMARY_COLUMNS
                }
            )
    with (run_dir / "validation_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=VALIDATION_COLUMNS)
        w.writeheader()
        w.writerows(validation)
    (run_dir / "tpch_all_queries.sql").write_text(
        "-- TPC-H Queries (Scale Factor: {})\n-- Target: {}\n-- Generated by harness.tpch_native (pocketstack №16)\n\n".format(
            meta["sf"], meta["target"]
        )
        + "".join(f"-- Query {q}\n{queries[q]};\n\n" for q in sorted(queries)),
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(build_summary_md(bench, validation, meta), encoding="utf-8")


def append_index(index: Path, meta: dict, bench: list[dict], validation: list[dict]) -> None:
    header = (
        "| run | commit | sf | N | target | parity | answers | file Σp50, мс | ducklake Σp50, мс |\n"
        "|---|---|---|---|---|---|---|---|---|"
    )
    file_sum = sum(r["p50_time_ms"] for r in bench if r["target"] == "file" and r["p50_time_ms"])
    lake_sum = sum(
        r["p50_time_ms"] for r in bench if r["target"] == "ducklake" and r["p50_time_ms"]
    )
    row = (
        f"| {meta['run']} | `{meta['commit']}` | {meta['sf']} | {meta['n']} | {meta['target']} "
        f"| {sum(1 for v in validation if v['parity'] == 'OK')}/{len(validation)} "
        f"| {sum(1 for v in validation if v['answers'] == 'OK')}/{len(validation)} "
        f"| {file_sum:.0f} | {lake_sum:.0f} |"
    )
    existing = index.read_text(encoding="utf-8") if index.exists() else ""
    if "| run | commit |" in existing:
        updated = existing.rstrip("\n") + "\n" + row + "\n"
    else:
        updated = (
            "# Журнал нативных TPC-H прогонов (results/native/*)\n\n" + header + "\n" + row + "\n"
        )
    index.write_text(updated, encoding="utf-8")


# --------------------------------------------------------------- cli ----------
def _git(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "n/a"


def _queries_label(ids: list[int]) -> str:
    if ids == list(range(1, 23)):
        return "Q1–Q22 (22)"
    return "Q" + ", Q".join(str(i) for i in ids) + f" ({len(ids)})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Нативный TPC-H bench: file vs ducklake (№16)")
    parser.add_argument("sf", nargs="?", type=float, default=1.0, help="scale factor (default 1)")
    parser.add_argument("--n", type=int, default=3, help="итераций на запрос (default 3)")
    parser.add_argument(
        "--target",
        choices=["file", "ducklake", "both"],
        default="both",
        help="окружение: file | ducklake | both (default both)",
    )
    parser.add_argument(
        "--queries", type=str, help="список query_nr, напр. '1,5,9' (default все 22)"
    )
    parser.add_argument("--skip-answers", action="store_true", help="не сверять с tpch_answers()")
    parser.add_argument("--bootstrap-only", action="store_true", help="только подготовка данных")
    args = parser.parse_args(argv)

    from harness.env import load_env

    load_env()  # DUCKLAKE_* из .env (как harness.bench)

    here = Path(__file__).resolve().parent.parent  # packages/harness
    repo = here.parent.parent
    ids = [int(x) for x in args.queries.split(",")] if args.queries else list(range(1, 23))

    bootstrap(repo, args.sf, lake=args.target != "file")

    if args.bootstrap_only:
        return 0

    tpch = duckdb.connect()
    cons = {}
    if args.target in ("file", "both"):
        cons["file"] = open_file_target(repo, args.sf)
    if args.target in ("ducklake", "both"):
        cons["ducklake"] = open_lake_target()
    run_id = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    try:
        queries = get_queries(tpch, ids)
        detail, bench, validation = run_benchmark(
            cons,
            queries,
            n=args.n,
            sf=args.sf,
            answers_con=None if args.skip_answers else tpch,
        )
        meta = {
            "run": run_id,
            "commit": _git(repo),
            "sf": sf_key(args.sf),
            "n": args.n,
            "target": {"file": "file", "ducklake": "ducklake", "both": "file + ducklake"}[
                args.target
            ],
            "queries": _queries_label(ids),
            "answers": (
                "выкл (--skip-answers)" if args.skip_answers else f"вкл (sf={sf_key(args.sf)})"
            ),
            "duckdb": duckdb.__version__,
        }
        run_dir = repo / "results" / "native" / run_id
        write_run(detail, bench, validation, queries, run_dir, meta)
        append_index(repo / "results" / "native" / "index.md", meta, bench, validation)
    finally:
        for con in cons.values():
            con.close()
        tpch.close()

    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"Прогон: {run_dir}\nЖурнал: {repo / 'results' / 'native' / 'index.md'}")
    ok = (
        all(v["parity"] in ("OK", "—") for v in validation)
        and all(v["answers"] in ("OK", "n/a", "—") for v in validation)
        and all(r["status"] == "success" for r in bench)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
