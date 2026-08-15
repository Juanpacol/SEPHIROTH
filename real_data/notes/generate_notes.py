"""
Generate realistic, 100%-synthetic clinical notes from the parsed Synthea
patients in `real_data/patients/sample_patients.json`.

This plays the same role as `synthetichealth/chatty-notes` (Apache 2.0,
https://github.com/synthetichealth/chatty-notes) — turning structured
synthetic patient data into narrative clinical text via an LLM — but
reuses SEPHIROTH's own Gemini client (`intelligence.llm.get_llm_client()`)
directly on the timeline data this project already parsed, instead of
re-implementing chatty-notes' FHIR-bundle ingestion from scratch.

Run manually (requires GEMINI_API_KEY, burns free-tier quota — never runs
in CI/tests):

    PYTHONPATH=.:platform python3 real_data/notes/generate_notes.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

SAMPLE_PATIENTS_PATH = Path(__file__).parent.parent / "patients" / "sample_patients.json"
OUTPUT_PATH = Path(__file__).parent / "sample_notes.json"

NOTE_PROMPT = """You are a physician writing a brief outpatient progress note.
Write ONE realistic clinical note (120-200 words, plain prose, no markdown)
for this patient encounter, based ONLY on the facts below — do not invent
any clinical detail not present in the data.

Patient: {age}-year-old {sex}
Active conditions: {conditions}
Current medications: {medications}
Recent timeline events: {timeline}

Write the note as a clinician would, in the style of a real EHR progress
note (chief complaint / relevant history / assessment / plan), referencing
only the facts given."""


def _patient_summary(patient: Dict[str, Any]) -> Dict[str, str]:
    timeline_str = "; ".join(f"{e['date']}: {e['title']}" for e in patient["timeline"][-5:])
    return {
        "age": str(patient["age"]),
        "sex": "female" if patient["sex"] == "F" else "male",
        "conditions": ", ".join(patient["conditions"][:6]) or "none recorded",
        "medications": ", ".join(patient["medications"]) or "none recorded",
        "timeline": timeline_str or "no recent events",
    }


async def generate_all(limit: int = 15) -> List[Dict[str, str]]:
    from intelligence.llm import get_llm_client  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    client = get_llm_client()
    patients = json.loads(SAMPLE_PATIENTS_PATH.read_text())[:limit]

    notes = []
    for patient in patients:
        summary = _patient_summary(patient)
        result = await client.chat(messages=[{"role": "user", "content": NOTE_PROMPT.format(**summary)}])
        notes.append(
            {
                "patient_id": patient["id"],
                "note_date": patient["timeline"][-1]["date"] if patient["timeline"] else "2026-01-01",
                "content": result.content.strip(),
            }
        )
        print(f"Generated note for {patient['name']} ({patient['id']})")
    return notes


def main() -> int:
    notes = asyncio.run(generate_all())
    with open(OUTPUT_PATH, "w") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(notes)} notes to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
