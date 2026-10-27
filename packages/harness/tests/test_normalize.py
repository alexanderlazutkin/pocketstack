"""Юнит-тесты нормализации (TDD, RED до реализации harness.normalize)."""

from decimal import Decimal

from harness.normalize import hash_sql, norm_key, norm_measure, norm_rows, norm_sql


class TestNormKey:
    def test_int_passthrough(self):
        assert norm_key(1992) == "1992"

    def test_float_integral(self):
        assert norm_key(1992.0) == "1992"

    def test_string_numeric(self):
        assert norm_key("1992") == "1992"

    def test_string_float_integral(self):
        assert norm_key("1992.0") == "1992"

    def test_string_stripped(self):
        assert norm_key(" EUROPE ") == "EUROPE"

    def test_none(self):
        assert norm_key(None) == ""

    def test_decimal(self):
        assert norm_key(Decimal(5)) == "5"


class TestNormMeasure:
    def test_string_to_decimal2(self):
        assert norm_measure("27504349883.7301") == Decimal("27504349883.73")

    def test_float_to_decimal2(self):
        assert norm_measure(33040602105.2891) == Decimal("33040602105.29")

    def test_decimal_passthrough(self):
        assert norm_measure(Decimal("12.345")) == Decimal("12.35")

    def test_negative(self):
        assert norm_measure("-1.004") == Decimal("-1.00")


class TestNormRows:
    def test_key_and_measure_split(self):
        rows = [("1992.0", "100.005"), (1992, 100.005)]
        out = norm_rows(rows, key_cols=1)
        assert (
            out
            == [
                ("1992", Decimal("100.01")),
            ]
            * 2
        )

    def test_two_keys(self):
        out = norm_rows([("EU", 1996.0, "5.555")], key_cols=2)
        assert out == [("EU", "1996", Decimal("5.56"))]


class TestSqlNormalization:
    RAW = 'SELECT  "a" . x ,  sum(b)\n FROM t\n GROUP BY 1'

    def test_whitespace_collapsed(self):
        assert norm_sql(self.RAW) == 'SELECT "a" . x , sum(b) FROM t GROUP BY 1'

    def test_hash_stable(self):
        assert hash_sql(self.RAW) == hash_sql('SELECT  "a" . x , sum(b) FROM t GROUP BY 1')

    def test_hash_differs_on_change(self):
        assert hash_sql(self.RAW) != hash_sql(self.RAW + " LIMIT 1")

    def test_hash_hex(self):
        h = hash_sql(self.RAW)
        assert len(h) == 64 and int(h, 16) >= 0
