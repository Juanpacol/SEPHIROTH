"""Timeline extractor tests — deterministic lexicon fallback path (no LLM)."""

import pytest

from intelligence.nlp.timeline_extractor import _fallback_extract, extract_events


class BrokenClient:
    """Simulates an unreachable Ollama server."""

    async def generate_json(self, *args, **kwargs):
        raise ConnectionError("ollama down")


def test_fallback_extracts_entities_with_note_date():
    events = _fallback_extract(
        "Patient diagnosed with hypertension, started lisinopril.", "2026-01-15"
    )
    titles = [e.title for e in events]
    assert any("hypertension" in t for t in titles)
    assert any("lisinopril" in t for t in titles)
    assert all(e.date == "2026-01-15" for e in events)


def test_fallback_prefers_date_found_in_text():
    events = _fallback_extract("On 2024-05-02 started metformin.", "2026-01-15")
    assert events and events[0].date == "2024-05-02"


@pytest.mark.asyncio
async def test_extract_events_falls_back_when_llm_fails():
    events = await extract_events(
        BrokenClient(), "Patient with diabetes on insulin.", "2026-02-01"
    )
    assert events, "fallback should still produce events"
    assert all(e.date == "2026-02-01" for e in events)
