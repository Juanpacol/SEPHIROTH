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


def test_the_pdf_names_agents_by_function_not_by_id():
    """AB#37. Page text is compressed in the file, so check the strings the
    renderer is handed rather than the bytes."""
    from api import pdf_export

    seen = []
    original = pdf_export._para
    pdf_export._para = lambda text, style: (seen.append(text), original(text, style))[1]
    try:
        consultation = _consultation(agents=["drug-safety", "evidence", "coordinator"])
        pdf_export.render_consultation_pdf(
            consultation, {"steps": [{"agent": "radiology", "action": "Described the image"}]}
        )
    finally:
        pdf_export._para = original

    joined = " | ".join(seen)
    assert "Medication Interactions, Guidelines &amp; Literature, coordinator" in joined or (
        "Medication Interactions, Guidelines & Literature, coordinator" in joined
    )
    assert "[Image Analysis] Described the image" in joined
    assert "drug-safety" not in joined
