"""`check_scope` — the clinical-scope guard that rejects clearly
non-medical questions before they reach routing or any model call.

The pair that matters most: a lay-language symptom question must NEVER be
flagged (that's the exact case the guard exists alongside — see
`data/rag/corpus_primary_care.py`), while an unambiguous off-topic question
(taxes, legal advice, code, a recipe) must be, in English and Spanish."""

from sephiroth.safety.scope import check_scope


def test_clean_clinical_query_has_no_flags():
    assert check_scope("What is the first-line therapy for type 2 diabetes?") == []


def test_lay_symptom_question_is_never_flagged():
    """The motivating case: this must reach the evidence specialist, not be
    rejected as out of scope."""
    assert check_scope("What do I do if I have a headache?") == []
    assert check_scope("Qué hago si tengo dolor de cabeza") == []


def test_tax_question_is_flagged():
    flags = check_scope("What do the guidelines recommend for filing quarterly small-business tax returns?")
    assert len(flags) == 1
    assert flags[0].code == "out_of_scope"


def test_tax_question_is_flagged_in_spanish():
    assert check_scope("Cómo hago la declaración de impuestos trimestrales?") != []


def test_legal_advice_is_flagged():
    assert check_scope("I need legal advice on how to file a lawsuit against my landlord") != []


def test_programming_question_is_flagged():
    assert check_scope("Can you write some python code to sort a list?") != []


def test_recipe_question_is_flagged():
    assert check_scope("What's a good recipe for chocolate chip cookies?") != []


def test_empty_or_none_query_has_no_flags():
    assert check_scope("") == []
    assert check_scope(None) == []
