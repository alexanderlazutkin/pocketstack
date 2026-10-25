"""Markdown-отчёт прогона harness: вопрос → rows-паритет / SQL-детерминизм / ground truth."""

import datetime
import subprocess
from pathlib import Path

OK, FAIL = "✅", "❌"


def _git(path: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return "n/a"


def write_report(results: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# pocketstack verify-report",
        "",
        f"_сгенерирован: {datetime.datetime.now().isoformat(timespec='seconds')}, "
        f"commit `{_git(path.parent.parent)}`_",
        "",
        "| Вопрос | rows: REST↔SQLAPI↔REF | SQL-hash (N прогонов) | ground truth (лог DuckDB) |",
        "|---|---|---|---|",
    ]
    parity = results.get("parity", {})
    determ = results.get("determinism", {})
    truth = results.get("ground_truth", {})

    for qid, p in parity.items():
        rows_cell = OK if p else FAIL
        d = determ.get(qid)
        det_cell = f"{OK} `{d[:12]}`" if d else (FAIL if d is False else "—")
        t = truth.get(qid)
        truth_cell = OK if t else (FAIL if t is False else "—")
        lines.append(f"| `{qid}` | {rows_cell} | {det_cell} | {truth_cell} |")

    total = len(parity)
    passed = sum(1 for v in parity.values() if v)
    det_ok = sum(1 for v in determ.values() if v)
    truth_ok = sum(1 for v in truth.values() if v)
    lines += [
        "",
        f"**Итог**: rows-паритет {passed}/{total}, SQL-детерминизм {det_ok}/{total}, "
        f"ground truth {truth_ok}/{total}.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
