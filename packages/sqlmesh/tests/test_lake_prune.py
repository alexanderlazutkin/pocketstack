"""TDD интеграционный тест чистки ducklake (--prune-old; Stage 7, шаг 8).

Опциональный (медленный): RUN_LAKE_TESTS=1 при поднятом ducklake-стеке
(docker compose up -d --wait). Проверяет приёмку шага 8:
- после seed --prune-old живой снапшот ровно один (time-travel свёрнут);
- ПОВТОРНЫЙ prune-rebuild не раздувает бакет (число объектов S3 стабильно);
- данные читаемы после чистки.

ВНИМАНИЕ по порядку: файл идёт по алфавиту ПЕРЕД test_lake_seed.py, который
в конце восстанавливает raw в sf=1 — итоговое состояние lake не портится.
"""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # packages/sqlmesh → seed_tpch

import seed_tpch

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LAKE_TESTS") != "1",
    reason="RUN_LAKE_TESTS!=1 — нужен ducklake-стек (docker compose up -d --wait)",
)

REPO = Path(__file__).resolve().parents[3]


def _snapshots(con) -> list:
    return con.execute("SELECT snapshot_id FROM ducklake_snapshots('lake') ORDER BY 1").fetchall()


def _s3_object_count() -> int:
    """Число объектов в бакете через mc внутри контейнера minio (compose-проект репо).

    Грабли (проверено): (1) у mc из образа elestio НЕТ `find --type`;
    (2) env $S3_ACCESS_KEY есть только в minio-init, в minio-сервере —
    $MINIO_ROOT_USER/$MINIO_ROOT_PASSWORD; (3) `... | wc -l` внутри sh
    маскирует падение mc (exit пайпа = exit wc) — строки считаем в python.
    """
    out = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "minio",
            "sh",
            "-c",
            "mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD "
            f">/dev/null && mc ls --recursive local/{os.environ['DUCKLAKE_S3_BUCKET']}",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    return len(lines)


def test_prune_old_bounds_snapshots_and_bucket(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_MODE", "ducklake")  # main() читает режим из env
    seed_tpch.seed_ducklake(0.1)  # без prune: накапливаем time-travel

    con = duckdb.connect()
    try:
        seed_tpch.lake_attach(con)
        assert len(_snapshots(con)) >= 2, "до prune должна быть история time-travel"
    finally:
        con.close()

    seed_tpch.seed_ducklake(0.1, prune_old=True)
    seed_tpch.seed_ducklake(0.1, prune_old=True)  # повторный rebuild
    objects_after_first_prune = _s3_object_count()

    con = duckdb.connect()
    try:
        seed_tpch.lake_attach(con)
        snaps = _snapshots(con)
        assert len(snaps) == 1, (
            f"после --prune-old живых снапшотов должно быть 1, есть {len(snaps)}"
        )
        # данные читаемы после чистки (sf=0.1: region/nation — константы dbgen)
        assert con.execute("SELECT COUNT(*) FROM lake.raw_tpch.region").fetchone()[0] == 5
    finally:
        con.close()

    seed_tpch.main(["--prune-old"])  # prune-only режим (финальный шаг rebuild-lake)
    objects_after_prune_only = _s3_object_count()
    con = duckdb.connect()
    try:
        seed_tpch.lake_attach(con)
        assert len(_snapshots(con)) == 1
    finally:
        con.close()

    assert objects_after_prune_only == objects_after_first_prune, (
        f"повторный rebuild раздувает бакет: {objects_after_first_prune} → {objects_after_prune_only}"
    )
