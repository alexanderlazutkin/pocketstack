# Нативный TPC-H: file vs DuckLake

## Параметры прогона

| Параметр | Значение |
|---|---|
| запуск | 2026-10-31T171508 |
| commit | `d8e8a50` |
| sf | 1 |
| итераций на запрос (N) | 3 |
| цель | file + ducklake |
| запросы | Q1–Q22 (22) |
| answers (tpch_answers) | вкл (sf=1) |
| duckdb | 1.5.5 |

22 запроса `tpch_queries()` к dbgen-данным без семантического слоя:
file — dbgen-файл `warehouse/tpch_native_sf*.duckdb`; ducklake — та же схема
в каталоге lake (pg + parquet в MinIO, READ_ONLY). Протокол: docs/bench-native-tpch.md;
пошаговое воспроизведение: docs/user-guide-tpch-benchmark.md.

| Q | rows | parity | answers | file p50 (min), мс | ducklake p50 (min), мс |
|---|---|---|---|---|---|
| Q01 | 4 | OK | OK | 12 (9) | 29 (25) |
| Q02 | 100 | OK | OK | 9 (8) | 35 (33) |
| Q03 | 10 | OK | OK | 10 (10) | 32 (26) |
| Q04 | 5 | OK | OK | 10 (10) | 19 (18) |
| Q05 | 5 | OK | OK | 9 (9) | 36 (35) |
| Q06 | 1 | OK | OK | 2 (2) | 11 (10) |
| Q07 | 4 | OK | OK | 12 (11) | 40 (39) |
| Q08 | 2 | OK | OK | 10 (9) | 48 (45) |
| Q09 | 175 | OK | OK | 40 (38) | 59 (58) |
| Q10 | 20 | OK | OK | 24 (23) | 60 (57) |
| Q11 | 1048 | OK | OK | 5 (4) | 18 (16) |
| Q12 | 2 | OK | OK | 8 (8) | 21 (20) |
| Q13 | 42 | OK | OK | 27 (26) | 42 (39) |
| Q14 | 1 | OK | OK | 8 (8) | 20 (19) |
| Q15 | 1 | OK | OK | 5 (5) | 15 (13) |
| Q16 | 18314 | OK | OK | 18 (17) | 31 (31) |
| Q17 | 1 | OK | OK | 8 (8) | 25 (24) |
| Q18 | 57 | OK | OK | 23 (23) | 41 (40) |
| Q19 | 1 | OK | OK | 12 (11) | 32 (31) |
| Q20 | 186 | OK | OK | 11 (10) | 31 (30) |
| Q21 | 100 | OK | OK | 36 (35) | 82 (82) |
| Q22 | 7 | OK | OK | 15 (14) | 29 (29) |

**Итог**: Σp50 file 313 / ducklake 758 мс (Σavg 319 / 798); медиана p50 file 10.8 / 31.5 мс; parity 22/22; answers 22/22.
