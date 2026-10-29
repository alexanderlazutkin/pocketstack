"""Фабрика ground-truth подключений к витрине (Stage 7: file | ducklake).

Режим — переменная окружения WAREHOUSE_MODE (default file, см. .env.example):
- file:     read-only коннект к warehouse/pocketstack.duckdb (как раньше);
- ducklake: :memory: + ATTACH каталога READ_ONLY + USE lake (модуль seed_tpch
  из workspace-пакета pocketstack-sqlmesh; DUCKLAKE_* — из .env).

Единая точка для conftest-фикстуры и harness.bench: ground-truth путь всегда
смотрит на ТО ЖЕ хранилище, что и Cube (иначе parity-тесты бессмысленны).
"""

import os
from pathlib import Path

import duckdb


def warehouse_connect(repo: Path) -> duckdb.DuckDBPyConnection:
    mode = os.environ.get("WAREHOUSE_MODE", "file")
    if mode == "ducklake":
        from seed_tpch import lake_attach

        con = duckdb.connect()
        # alias pocketstack — логическое имя хранилища: так каталог адресуют
        # семантическая модель Cube и референсный SQL тестов (test_rbac и др.)
        lake_attach(con, read_only=True, alias="pocketstack")
        con.execute("USE pocketstack")
        return con
    if mode != "file":
        raise SystemExit(f"Неизвестный WAREHOUSE_MODE={mode} (допустимо file|ducklake)")
    return duckdb.connect(str(repo / "warehouse" / "pocketstack.duckdb"), read_only=True)
