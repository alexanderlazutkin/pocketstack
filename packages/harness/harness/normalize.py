"""Нормализация значений и SQL для сквозного сравнения трёх путей выполнения.

REST /v1/load отдаёт меры строками полной точности, SQL API (pg-wire) —
float/Decimal, reference (DuckDB) — Decimal/int. Канонизация сводит всё
к кортежам (str-ключи, Decimal@2dp-меры).
"""

import hashlib
import re
from decimal import Decimal, ROUND_HALF_UP

_WS = re.compile(r"\s+")


def norm_key(value) -> str:
    """Канонический ключ измерения: integral-float → int → str, иначе str().strip()."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return str(int(value))
    s = str(value).strip()
    if re.fullmatch(r"-?\d+\.0+", s):  # "1992.0" → "1992"
        return str(int(float(s)))
    return s


def norm_measure(value) -> Decimal:
    """Каноническая мера: Decimal, округлённая до копеек (half-up)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def norm_rows(rows: list, key_cols: int) -> list[tuple]:
    """rows → [(ключи как str, меры как Decimal@2dp), ...]."""
    out = []
    for row in rows:
        keys = tuple(norm_key(v) for v in row[:key_cols])
        measures = tuple(norm_measure(v) for v in row[key_cols:])
        out.append(keys + measures)
    return out


def norm_sql(sql: str) -> str:
    """Схлопнуть пробелы/переводы строк — для хэша детерминизма и ground truth."""
    return _WS.sub(" ", sql or "").strip()


def hash_sql(sql: str) -> str:
    return hashlib.sha256(norm_sql(sql).encode()).hexdigest()
