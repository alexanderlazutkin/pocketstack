"""Контракт golden-вопросов (TDD, RED до реализации harness.golden)."""

from harness.golden import GOLDEN


def test_has_12_questions():
    assert len(GOLDEN) == 12


def test_unique_ids():
    ids = [g["id"] for g in GOLDEN]
    assert len(ids) == len(set(ids))


def test_every_question_is_nonempty_russian():
    for g in GOLDEN:
        assert isinstance(g["question"], str) and g["question"].strip()
        assert g["question"].endswith("?")


def test_rest_query_shape():
    for g in GOLDEN:
        q = g["rest"]
        assert q.get("measures"), g["id"]
        for member in q["measures"] + q.get("dimensions", []):
            assert member.startswith("sales."), f"{g['id']}: {member} не из view sales"


def test_sqlapi_shape():
    for g in GOLDEN:
        s = g["sqlapi"].strip()
        assert s.upper().startswith("SELECT"), g["id"]
        assert " FROM sales" in s, g["id"]


def test_reference_shape():
    for g in GOLDEN:
        r = g["reference"].strip()
        assert r.upper().startswith("SELECT"), g["id"]
        assert "marts.fact_sales" in r, g["id"]


def test_key_cols_positive():
    for g in GOLDEN:
        assert isinstance(g["key_cols"], int) and g["key_cols"] >= 0, g["id"]
        # число ключей = числу dimensions в REST-запросе
        dims = len(g["rest"].get("dimensions", [])) + len(g["rest"].get("timeDimensions", []))
        assert g["key_cols"] == dims, g["id"]


def test_ordered_flag_default_false():
    for g in GOLDEN:
        assert isinstance(g.get("ordered", False), bool)


def test_limit_only_when_ordered():
    """top-N вопросы обязаны иметь limit и ordered=True."""
    for g in GOLDEN:
        has_limit = "limit" in g["rest"]
        assert has_limit == g.get("ordered", False), g["id"]
        if has_limit:
            assert "LIMIT" in g["sqlapi"].upper(), g["id"]
            assert "LIMIT" in g["reference"].upper(), g["id"]


def test_filters_reflected_everywhere():
    """Если в REST есть фильтр — он должен быть и в SQL API, и в reference."""
    for g in GOLDEN:
        filters = g["rest"].get("filters", [])
        if filters:
            assert "WHERE" in g["sqlapi"].upper(), g["id"]
            assert "WHERE" in g["reference"].upper(), g["id"]
