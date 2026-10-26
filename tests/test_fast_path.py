"""`api.fast_path.try_fast_path` — the no-LLM router that bypasses the
multi-agent pipeline for pure data retrieval. The safety argument (nothing
synthesized -> nothing to hallucinate) only holds if the router stays
conservative about *what* it claims; the exclusion tests here are the
ones that matter most, not the happy path.

Runs against the real `ToolRuntime` (RAG's seeded corpus, the curated
drug-interaction table) — no API key needed, since `tests/conftest.py`'s
autouse `no_gemini_key` fixture forces RAG's keyword-only fallback path,
which is deterministic."""

import pytest

from api.fast_path import _format_rag_answer, try_fast_path
from core.config import settings
from data.schemas import Patient

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# `_format_rag_answer` — pure, no fixtures needed
# --------------------------------------------------------------------------


def test_format_rag_answer_uses_citation_when_present():
    answer, citations = _format_rag_answer(
        [{"content": "Do the thing.", "citation": "Real Guideline, Org, 2024", "source": "Org Guideline"}]
    )
    assert citations == ["Real Guideline, Org, 2024"]
    assert "[Real Guideline, Org, 2024]" in answer


def test_format_rag_answer_falls_back_to_source_when_no_citation():
    answer, citations = _format_rag_answer(
        [{"content": "Do the thing.", "citation": "", "source": "Fallback Source"}]
    )
    assert citations == ["Fallback Source"]


def test_format_rag_answer_returns_none_when_neither_citation_nor_source_exists():
    """Regression test: the old code substituted the literal string
    "uncited" here, which could land in `citation_report["verified"]" and
    mark a citation that doesn't exist as verified. It must bail instead,
    letting the caller fall through to the full pipeline."""
    assert _format_rag_answer([{"content": "Do the thing.", "citation": "", "source": ""}]) is None


# --------------------------------------------------------------------------
# Similarity floor — a weak top hit must fall through, not become the answer
# --------------------------------------------------------------------------


async def test_guideline_query_falls_through_when_top_score_is_below_floor(db_session, monkeypatch):
    from api import fast_path as fast_path_module

    class _WeakRegistry:
        async def load(self):
            return None

        async def execute(self, name, args):
            assert name == "search_clinical_guidelines"
            return {
                "results": [
                    {
                        "id": "weak-hit",
                        "content": "Coincidentally overlapping text.",
                        "citation": "Some Guideline, 2024",
                        "source": "Some Guideline",
                        "score": settings.fast_path_min_score / 2,
                    }
                ]
            }

    monkeypatch.setattr(fast_path_module, "get_tool_runtime", lambda: _WeakRegistry())
    result = await try_fast_path(
        "What is the first-line treatment for hypertension?", patient_id="", context={}, session=db_session
    )
    assert result is None


async def test_drug_interaction_query_triggers_with_two_plus_meds(db_session):
    result = await try_fast_path(
        "Do warfarin and furosemide interact?",
        patient_id="",
        context={"medications": ["warfarin", "furosemide", "digoxin"]},
        session=db_session,
    )
    assert result is not None
    assert result["source"] == "drug-safety"
    assert result["tool_calls"][0]["name"] == "check_drug_interactions"
    # Regression: a missing "agent" key here renders "unknown" in the
    # explainability panel — src/sephiroth/telemetry/explain.py falls back
    # to that literal string when a tool_call lacks it.
    assert result["tool_calls"][0]["agent"] == "drug-safety"


async def test_drug_interaction_query_extracts_medications_named_in_the_query(db_session):
    """No context, no patient — the drug names are in the question itself
    ("do warfarin and ibuprofen interact?"), which must still resolve."""
    result = await try_fast_path(
        "Do warfarin and ibuprofen interact?",
        patient_id="",
        context={},
        session=db_session,
    )
    assert result is not None
    assert result["source"] == "drug-safety"
    assert set(result["tool_calls"][0]["arguments"]["medications"]) == {"warfarin", "ibuprofen"}


async def test_drug_interaction_query_does_not_trigger_with_fewer_than_two_meds(db_session):
    result = await try_fast_path(
        "Does warfarin interact with anything?",
        patient_id="",
        context={"medications": ["warfarin"]},
        session=db_session,
    )
    assert result is None


async def test_drug_interaction_resolves_medications_from_patient_chart(db_session):
    patient = Patient(
        id="PFAST1",
        name="Fast Path Patient",
        age=50,
        sex="F",
        medical_record_number="PT-PFAST1",
        medications=["warfarin", "digoxin"],
    )
    db_session.add(patient)
    await db_session.commit()

    result = await try_fast_path(
        "Do this patient's medications interact?",
        patient_id="PFAST1",
        context={},
        session=db_session,
    )
    # Excluded by the patient-specific phrasing guard below (own test),
    # but the drug-interaction branch is checked first and doesn't apply
    # the same guard — medications are safely resolvable regardless of
    # phrasing since it's a deterministic table lookup, not synthesis.
    assert result is not None
    assert result["source"] == "drug-safety"


async def test_guideline_query_triggers_without_patient_id(db_session, monkeypatch):
    """The real `ToolRuntime` here runs RAG's keyword-only fallback (see
    module docstring) — `dense_similarity` is always `None` on that path, so
    it can never clear `fast_path_min_dense_similarity` on its own (the gap
    that path's lack of embedding corroboration deliberately leaves). A
    strong, explicit dense hit is mocked in instead so this test exercises
    the actually-supported case — embeddings available — rather than relying
    on the keyword score's unrelated, much larger scale to incidentally clear
    the floor the way it did before `dense_similarity` existed."""
    from api import fast_path as fast_path_module

    class _StrongRegistry:
        async def load(self):
            return None

        async def execute(self, name, args):
            assert name == "search_clinical_guidelines"
            return {
                "results": [
                    {
                        "id": "strong-hit",
                        "content": "First-line treatment for hypertension is a thiazide diuretic.",
                        "citation": "Real Guideline, Org, 2024",
                        "source": "Real Guideline",
                        "score": settings.fast_path_min_score * 2,
                        "dense_similarity": settings.fast_path_min_dense_similarity + 0.1,
                    }
                ]
            }

    monkeypatch.setattr(fast_path_module, "get_tool_runtime", lambda: _StrongRegistry())
    result = await try_fast_path(
        "What is the first-line treatment for hypertension?",
        patient_id="",
        context={},
        session=db_session,
    )
    assert result is not None
    assert result["source"] == "evidence"
    assert result["tool_calls"][0]["name"] == "search_clinical_guidelines"
    # Regression: a missing "agent" key here renders "unknown" in the
    # explainability panel — src/sephiroth/telemetry/explain.py falls back
    # to that literal string when a tool_call lacks it.
    assert result["tool_calls"][0]["agent"] == "evidence"
    assert result["citation_report"]["fabricated"] == []


async def test_guideline_query_falls_through_without_dense_corroboration(db_session, monkeypatch):
    """A hit can clear `fast_path_min_score` with no dense corroboration at
    all: the RRF formula alone can't tell a rank-0 *keyword* hit scored
    through several contributing matches from a rank-0 *dense* hit — only
    `dense_similarity` (or its absence) distinguishes them. Without this
    gate, that let keyword overlap alone fast-path an answer (live case: an
    IV vancomycin dosing question matched a Surviving Sepsis Campaign
    guideline on shared clinical vocabulary, `dense_similarity` just over
    `retrieval_min_similarity` but nowhere near confidently relevant)."""
    from api import fast_path as fast_path_module

    class _KeywordOnlyRegistry:
        async def load(self):
            return None

        async def execute(self, name, args):
            assert name == "search_clinical_guidelines"
            return {
                "results": [
                    {
                        "id": "keyword-only-hit",
                        "content": "Shares clinical vocabulary but isn't actually on topic.",
                        "citation": "Unrelated Guideline, 2024",
                        "source": "Unrelated Guideline",
                        "score": settings.fast_path_min_score * 2,
                        "dense_similarity": None,
                    }
                ]
            }

    monkeypatch.setattr(fast_path_module, "get_tool_runtime", lambda: _KeywordOnlyRegistry())
    result = await try_fast_path(
        "What is the first-line treatment for hypertension?",
        patient_id="",
        context={},
        session=db_session,
    )
    assert result is None


async def test_guideline_query_does_not_trigger_with_patient_id(db_session):
    """A patient_id present means specialist synthesis against that
    patient's real data may be needed — never fast-pathed."""
    result = await try_fast_path(
        "What is the first-line treatment for hypertension?",
        patient_id="P001",
        context={},
        session=db_session,
    )
    assert result is None


async def test_guideline_query_excluded_by_patient_specific_phrasing(db_session):
    """Even with no patient_id, "this patient's" phrasing signals a
    synthesis question, not a guideline lookup -- must fall through to
    the full pipeline. This is the exclusion
    `test_run_consultation_abstains_on_unsupported_high_risk_claim`
    depends on staying correct."""
    result = await try_fast_path(
        "What is the recommended target for this patient's blood pressure?",
        patient_id="",
        context={},
        session=db_session,
    )
    assert result is None


async def test_unrelated_query_returns_none(db_session):
    result = await try_fast_path(
        "Can you help me schedule a follow-up appointment?",
        patient_id="",
        context={},
        session=db_session,
    )
    assert result is None
