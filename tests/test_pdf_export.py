"""Tests for the consultation PDF export."""

from datetime import datetime, timezone
from types import SimpleNamespace

from api.pdf_export import render_consultation_pdf


def _consultation(**overrides):
    base = dict(
        id="abcdef1234567890",
        patient_id="P001",
        query="What A1C goal is appropriate?",
        answer="Target A1C <7% [ADA Standards of Care in Diabetes, 2024].",
        agents=["evidence", "coordinator"],
        citation_report={"verified": ["ADA Standards of Care in Diabetes, 2024"], "fabricated": []},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user=SimpleNamespace(name="Dr. Test"),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_render_consultation_pdf_returns_bytes():
    pdf_bytes = render_consultation_pdf(_consultation(), explanation={})
    assert pdf_bytes.startswith(b"%PDF")


def test_render_consultation_pdf_includes_reasoning_trace():
    explanation = {"steps": [{"agent": "evidence", "action": "Searched guidelines"}]}
    pdf_bytes = render_consultation_pdf(_consultation(), explanation)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100


def test_render_consultation_pdf_with_fabricated_citations():
    consultation = _consultation(citation_report={"verified": [], "fabricated": ["Fake Journal, 2099"]})
    pdf_bytes = render_consultation_pdf(consultation, explanation={})
    assert pdf_bytes.startswith(b"%PDF")


def test_render_consultation_pdf_no_patient_id():
    consultation = _consultation(patient_id=None, agents=[])
    pdf_bytes = render_consultation_pdf(consultation, explanation={})
    assert pdf_bytes.startswith(b"%PDF")
