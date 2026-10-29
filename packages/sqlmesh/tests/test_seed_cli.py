"""TDD unit-тесты CLI seed_tpch: флаг --prune-old (Stage 7, шаг 8).

Без инфраструктуры: проверяется только парсинг аргументов и маршрутизация
по WAREHOUSE_MODE (вызовы seed/prune — под monkeypatch). Интеграционные
проверки чистки снапшотов/бакета — test_lake_prune.py (RUN_LAKE_TESTS=1).
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # packages/sqlmesh → seed_tpch

import seed_tpch


def test_main_ducklake_plain_seed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        seed_tpch, "seed_ducklake", lambda sf, prune_old=False: calls.append((sf, prune_old))
    )
    monkeypatch.setenv("WAREHOUSE_MODE", "ducklake")
    seed_tpch.main(["2"])
    assert calls == [(2.0, False)]


def test_main_ducklake_seed_with_prune_old(monkeypatch):
    calls = []
    monkeypatch.setattr(
        seed_tpch, "seed_ducklake", lambda sf, prune_old=False: calls.append((sf, prune_old))
    )
    monkeypatch.setenv("WAREHOUSE_MODE", "ducklake")
    seed_tpch.main(["0.5", "--prune-old"])
    assert calls == [(0.5, True)]


def test_main_prune_old_without_sf_is_prune_only(monkeypatch):
    """`--prune-old` без sf — чистка БЕЗ пересева (финальный шаг rebuild-lake)."""
    seeded, pruned = [], []
    monkeypatch.setattr(seed_tpch, "seed_ducklake", lambda sf, prune_old=False: seeded.append(sf))
    monkeypatch.setattr(seed_tpch, "prune_old_snapshots", lambda con: pruned.append(True))
    monkeypatch.setattr(seed_tpch, "lake_attach", lambda con, **kw: None)
    monkeypatch.setattr("duckdb.connect", lambda *a, **kw: SimpleNamespace(close=lambda: None))
    monkeypatch.setenv("WAREHOUSE_MODE", "ducklake")
    seed_tpch.main(["--prune-old"])
    assert seeded == [] and pruned == [True]


def test_main_prune_old_rejected_in_file_mode(monkeypatch):
    monkeypatch.setattr(
        seed_tpch, "seed_file", lambda sf: pytest.fail("file-режим не должен запускаться")
    )
    monkeypatch.setattr(seed_tpch, "seed_ducklake", lambda sf, prune_old=False: pytest.fail("..."))
    monkeypatch.setenv("WAREHOUSE_MODE", "file")
    with pytest.raises(SystemExit, match="prune"):
        seed_tpch.main(["1", "--prune-old"])


def test_main_unknown_mode_rejected(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_MODE", "s3")
    with pytest.raises(SystemExit, match="WAREHOUSE_MODE"):
        seed_tpch.main(["1"])
