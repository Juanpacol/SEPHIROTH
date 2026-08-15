"""
Example: run the Intelligent Timeline extractor against realistic clinical
notes (real_data/notes/sample_notes.json), instead of hand-typed test
strings — exercises intelligence/nlp/timeline_extractor.py with more
varied clinical vocabulary than the unit tests use.

Uses the deterministic lexicon fallback if GEMINI_API_KEY isn't set
(same graceful degradation as the rest of the app); pass --llm to force
the real Gemini-backed extraction (burns free-tier quota).

Run from the repo root:

    PYTHONPATH=.:platform .venv/bin/python examples/real_data_example.py
    PYTHONPATH=.:platform .venv/bin/python examples/real_data_example.py --llm
"""

import asyncio
import json
import sys
from pathlib import Path

from intelligence.nlp.timeline_extractor import _fallback_extract, extract_events

NOTES_PATH = Path(__file__).parent.parent / "real_data" / "notes" / "sample_notes.json"


async def main(use_llm: bool) -> None:
    notes = json.loads(NOTES_PATH.read_text())

    for note in notes:
        print(f"\n--- Patient {note['patient_id'][:8]} ({note['note_date']}) ---")
        print(note["content"][:150] + "...")

        if use_llm:
            from intelligence.llm import get_llm_client

            events = await extract_events(get_llm_client(), note["content"], note["note_date"])
        else:
            events = _fallback_extract(note["content"], note["note_date"])

        print(f"Extracted {len(events)} timeline events:")
        for e in events:
            print(f"  [{e.date}] ({e.type}) {e.title}")


if __name__ == "__main__":
    asyncio.run(main(use_llm="--llm" in sys.argv))
