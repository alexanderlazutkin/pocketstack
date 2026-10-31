# Нативный TPC-H бенчмарк: DuckDB file vs DuckLake

Версия: 1.1 (2026-10-31 — артефакты в формате ducklake-sandbox + блок параметров
прогона + `--target`; пошаговый user guide выделен). Реализация:
`packages/harness/harness/tpch_native.py`, запуск `just bench-native [sf]`
(default sf=1). **Пошаговое воспроизведение: docs/user-guide-tpch-benchmark.md.**
Базис: наработки `ducklake-sandbox`, адаптированы.

## 1. Назначение

Чистый базлайн движка: 22 запроса TPC-H из расширения `tpch` (`tpch_queries()`)
против dbgen-данных, **без семантического слоя** (Cube/sqlmesh не участвуют).
Дополняет `bench-protocol.md` (там — сквозные пути через куб по 13 golden-вопросам;
здесь — сам DuckDB в двух физических раскладках):

| Цель | Физика | Данные |
|---|---|---|
| **file** | dbgen-файл `warehouse/tpch_native_sf<N>.duckdb`, таблицы в `main` | нативные таблицы DuckDB |
| **ducklake** | схема `tpch_native` в lake-каталоге (pg + parquet в MinIO), READ_ONLY attach | тот же dbgen, CTAS в parquet |

**Изоляция от демо-витрины**: bench не читает и не пишет демо-схемы (`raw_tpch`,
`marts`) — sf бенча независим от sf витрины (приём «отдельный dbgen-файл» из
решения №16: seed_tpch держит dbgen-таблицы только в raw_tpch, а бенчу нужен
main). Данные бенча управляются собственным bootstrap-ом и кэшируются по sf
(маркер `tpch_native_meta` в файле и в lake-схеме; повторный запуск с тем же sf
ничего не перегенерирует).

## 2. Методика

- Запросы: `tpch_queries()` Q1–Q22 дословно, без переписывания.
- Итерации: N=3 на цель (default; `--n`), статистика avg/min/max/p50/total,
  чередование целей внутри запроса (file → ducklake) — обе цели в равных условиях.
- **answers**: сверка результата эталонной цели (file; при её отсутствии —
  ducklake) с эталонами `tpch_answers()` (доступны sf 0.01 / 0.1 / 1; для прочих
  sf — `n/a`). Ответы TPC-H округлены до 2 знаков — числовые колонки
  сравниваются с допуском 0.005.
- **parity**: file ↔ ducklake построчно, порядок строк не важен (ORDER BY keys
  не задают полный порядок), числовая толерантность 1e-6/1e-9.
- Ошибка попытки не валит прогон: фиксируется в `status` (формат sandbox).
- DuckDB 1.5.5 (venv воркспейса, как весь стек).
- Нужна ducklake-инфраструктура для целей ducklake/both:
  `docker compose up -d --wait` (pg+minio); для `--target file` docker не нужен.

Опции CLI: `--n N`, `--target file|ducklake|both`, `--queries '1,5,9'`,
`--skip-answers`, `--bootstrap-only` (полная таблица — user guide §3).

## 3. Артефакты (results/native/, в git; формат ducklake-sandbox)

```
results/native/
├── index.md                       # журнал: run, commit, sf, N, target, parity, answers, Σp50
└── <YYYY-MM-DDTHHMMSS>/           # один прогон
    ├── benchmark_detailed_timing.csv  # каждая попытка: query,target,attempt,time_ms,rows,status
    ├── benchmark_summary.csv          # query × target: iterations, avg/min/max/p50/total, rows, status
    ├── validation_summary.csv         # query, parity(+reason), answers(+reason)
    ├── tpch_all_queries.sql           # все запросы дословно + шапка (Scale Factor, Target)
    └── summary.md                     # ОДНА таблица Q1–Q22 + блок «Параметры прогона» + итог Σ/медиана
```

`summary.md` начинается с блока **«Параметры прогона»**: запуск, commit, sf,
N итераций, цель (target), запросы, answers вкл/выкл, версия duckdb —
артефакт самодокументирован (проверялось: замечание по №16 от 2026-10-31).

Exit code: 0 — все parity/answers OK и все попытки success; 1 — есть FAIL/ошибка
(n/a и «—» провалом не считаются).

## 4. Интерпретация (первый прогон sf=1, 2026-10-31T164932)

**Σp50: file 310 / ducklake 752 мс; медиана p50: 11.4 / 31.0 мс; parity 22/22;
answers 22/22.**

| Наблюдение | Объяснение |
|---|---|
| ducklake ≈ 2–2.5× дороже file | каждый запрос тянет parquet из MinIO (S3-hop) — цена lake-формата; картина как у REF-пути в bench-protocol §1a |
| у ducklake p50 ≈ min | итерации 2–3 идут по прогретому кэшу (MinIO локальный); p50 устойчив |
| file: тяжелейшие Q21 (35 мс), Q9 (37 мс) | полный скан lineitem × 2–3; Q16 (18314 строк) дешевле — селективный фильтр |
| answers 22/22 | данные dbgen канонические; file-таргет эталонен, ducklake подтверждён parity |

Сравнение — только внутри sf (правила bench-protocol §6). Рост sf
(`just bench-native 10`) — новый ряд в index.md; answers для sf>1 недоступны
(эталоны tpch_answers() есть только до sf=1).

## 5. Хранение

- `warehouse/tpch_native_sf<N>.duckdb` — вне git (gitignore), регенерируется
  bootstrap-ом; sf=1 ≈ 250 МБ, sf=10 ≈ 9 ГБ.
- lake-схема `tpch_native` — в общем pg-каталоге/бакете; НЕ чистится
  `rebuild-lake` (prune гасит только старые снапшоты, схему не трогает).
  Полная зачистка: `DROP SCHEMA pocketstack.tpch_native CASCADE` (+ удалить файл).
