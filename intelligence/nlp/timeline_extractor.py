"""
Timeline extractor — turns free-text clinical notes into structured
Intelligent Timeline events using Ollama structured output, with a
deterministic lexicon fallback when the LLM is unavailable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List

from intelligence.llm import OllamaClient

logger = logging.getLogger(__name__)

EVENT_TYPES = ["diagnosis", "medication", "lab", "imaging", "event"]

EVENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "type": {"type": "string", "enum": EVENT_TYPES},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["date", "type", "title", "detail"],
            },
        }
    },
    "required": ["events"],
}

SYSTEM_PROMPT = (
    "You extract clinical timeline events from medical notes. "
    "Return every distinct diagnosis, medication start/stop/change, lab result, "
    "imaging study, and clinical event (admission, discharge, procedure) as its "
    "own event. Use the ISO date mentioned nearest to each event; if no date is "
    "mentioned for an event, use the note date provided. Titles are short "
    "(<=10 words); details hold values/doses. Never invent events."
)

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass
class ExtractedEvent:
    date: str
    type: str
    title: str
    detail: str


def _fallback_extract(note_text: str, note_date: str) -> List[ExtractedEvent]:
    """Deterministic fallback: lexicon entities + nearest ISO date in the text."""
    from intelligence.mcp.nlp_server import _extract_with_lexicon

    type_map = {
        "disease": "diagnosis",
        "medication": "medication",
        "procedure": "event",
        "symptom": "event",
    }
    dates = _DATE_RE.findall(note_text)
    default_date = dates[0] if dates else note_date

    events = []
    for entity in _extract_with_lexicon(note_text):
        events.append(
            ExtractedEvent(
                date=default_date,
                type=type_map.get(entity["entity_type"], "event"),
                title=f"{entity['entity_type'].capitalize()}: {entity['text']}",
                detail="Extracted by lexicon fallback",
            )
        )
    return events


async def extract_events(client: OllamaClient, note_text: str, note_date: str) -> List[ExtractedEvent]:
    """Extract timeline events from a clinical note (LLM-first, fallback-safe)."""
    try:
        payload = await client.generate_json(
            prompt=f"Note date: {note_date}\n\nClinical note:\n{note_text}",
            schema=EVENTS_SCHEMA,
            system_prompt=SYSTEM_PROMPT,
        )
        events = []
        for raw in payload.get("events", []):
            if not _DATE_RE.match(raw.get("date", "")):
                raw["date"] = note_date
            if raw.get("type") not in EVENT_TYPES:
                raw["type"] = "event"
            if raw.get("title"):
                events.append(
                    ExtractedEvent(
                        date=raw["date"],
                        type=raw["type"],
                        title=raw["title"][:200],
                        detail=raw.get("detail", "")[:500],
                    )
                )
        return events
    except Exception:
        logger.exception("LLM timeline extraction failed; using lexicon fallback")
        return _fallback_extract(note_text, note_date)
