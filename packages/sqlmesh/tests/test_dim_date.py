"""TDD: измерение календаря marts.dim_date.

Диапазон: min/max по union ship_date + receipt_date из fact_sales
(LEAST/GREATEST по обеим колонкам). Grain — день, без пропусков.
Атрибуты: year, quarter, month, day.

Пока `just apply` не пересобран с моделью dim_date — таблица отсутствует, тесты RED.
"""

from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[3]
WAREHOUSE = REPO / "warehouse" / "pocketstack.duckdb"

COLUMNS = {"date_day", "year", "quarter", "month", "day"}


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(WAREHOUSE), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def dim_date(con):
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        ).fetchall()
    }
    if "dim_date" not in tables:
        pytest.fail("marts.dim_date отсутствует: добавьте модель и выполните `just apply`")
    return tables


@pytest.fixture(scope="module")
def bounds(con):
    (min_d, max_d) = con.execute(
        "SELECT min(least(ship_date, receipt_date)), max(greatest(ship_date, receipt_date)) "
        "FROM marts.fact_sales"
    ).fetchone()
    return min_d, max_d


def test_column_contract(con, dim_date):
    got = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'marts' AND table_name = 'dim_date'"
        ).fetchall()
    }
    assert got == COLUMNS, f"лишние={got - COLUMNS}, отсутствуют={COLUMNS - got}"


def test_rowcount_full_range(con, dim_date, bounds):
    min_d, max_d = bounds
    expected_days = (max_d - min_d).days + 1
    n = con.execute("SELECT COUNT(*) FROM marts.dim_date").fetchone()[0]
    assert n == expected_days, f"dim_date: {n} != {expected_days} (диапазон {min_d}..{max_d})"


def test_no_gaps_no_dupes(con, dim_date, bounds):
    min_d, max_d = bounds
    row = con.execute(
        "SELECT min(date_day), max(date_day), count(*), count(DISTINCT date_day) FROM marts.dim_date"
    ).fetchone()
    assert row[0] == min_d, f"min {row[0]} != {min_d}"
    assert row[1] == max_d, f"max {row[1]} != {max_d}"
    assert row[2] == row[3], "дубликаты date_day"
    # непрерывность: соседние дни отличаются ровно на 1
    gaps = con.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT date_day, lead(date_day) OVER (ORDER BY date_day) AS nxt FROM marts.dim_date"
        ") WHERE nxt IS NOT NULL AND date_diff('day', date_day, nxt) <> 1"
    ).fetchone()[0]
    assert gaps == 0, f"пропусков: {gaps}"


@pytest.mark.parametrize(
    "attr,expr",
    [
        ("year", "year(date_day)"),
        ("quarter", "quarter(date_day)"),
        ("month", "month(date_day)"),
        ("day", "day(date_day)"),
    ],
)
def test_attributes(con, dim_date, attr, expr):
    bad = con.execute(f"SELECT COUNT(*) FROM marts.dim_date WHERE {attr} <> {expr}").fetchone()[0]
    assert bad == 0, f"dim_date.{attr}: {bad} строк не соответствуют дате"


def test_fk_ship_date(con, dim_date):
    """Календарь покрывает ship_date факта (роль shipping calendar)."""
    orphans = con.execute(
        "SELECT COUNT(*) FROM marts.fact_sales f LEFT JOIN marts.dim_date d "
        "ON d.date_day = f.ship_date WHERE d.date_day IS NULL"
    ).fetchone()[0]
    assert orphans == 0, f"ship_date без календаря: {orphans}"


def test_fk_receipt_date(con, dim_date):
    """Календарь покрывает и receipt_date (union-диапазон)."""
    orphans = con.execute(
        "SELECT COUNT(*) FROM marts.fact_sales f LEFT JOIN marts.dim_date d "
        "ON d.date_day = f.receipt_date WHERE d.date_day IS NULL"
    ).fetchone()[0]
    assert orphans == 0, f"receipt_date без календаря: {orphans}"
