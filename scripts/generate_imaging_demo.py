"""Writes the demo imaging analyses: the real Vision AI pipeline run once over
the images bundled in `platform/api/static/imaging-demo/`.

    LLM_PROVIDER=gemini PYTHONPATH=.:platform .venv/bin/python scripts/generate_imaging_demo.py

The output, `analyses.json` next to the images, is committed: a deployment shows
exactly what the model said, with the model and date, and never calls the model
at request time. Re-run it (and review the diff) when an image or the prompt
changes. It sends the bundled images to the configured vision model, so run it
only with a provider you are willing to send them to.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from datetime import date
from pathlib import Path

from core.config import settings
from intelligence.mcp.vision_server import (
    DESCRIPTION_PROMPT,
    _active_vision_model_name,
)
from sephiroth.models import get_llm_client

MIN_WORDS = 40
# Well above the 220 the live endpoint allows: with the cloud model, hidden
# reasoning tokens count against the cap and a tight one cuts the answer off
# mid-sentence. The prompt itself still asks for under 130 words.
OUTPUT_TOKENS = 1500
DEMO_DIR = Path(__file__).resolve().parents[1] / "platform" / "api" / "static" / "imaging-demo"

#: file -> (modality shown in the card title, anatomical region)
STUDIES = {
    "xray.webp": ("XRAY", "Chest"),
    "ct-brain.webp": ("CT", "Brain"),
    "mri-brain.webp": ("MRI", "Brain"),
    "ultrasound.webp": ("ULTRASOUND", "Obstetric"),
}


async def main() -> None:
    client = get_llm_client()
    model = _active_vision_model_name(settings)
    analyses = []
    for name, (modality, region) in STUDIES.items():
        path = DEMO_DIR / name
        # The model sometimes stops after one sentence; a card with six words is
        # not an analysis, so ask again (a few times) rather than commit it.
        for _ in range(4):
            text = await client.describe_image(
                image_bytes=path.read_bytes(),
                mime_type=mimetypes.guess_type(name)[0] or "image/webp",
                prompt=DESCRIPTION_PROMPT,
                max_output_tokens=OUTPUT_TOKENS,
            )
            if len(text.split()) >= MIN_WORDS and text.rstrip().endswith((".", ")")):
                break
        else:
            raise SystemExit(
                f"{name}: the model did not give a complete answer of at least {MIN_WORDS} words"
            )
        analyses.append(
            {
                "file": name,
                "modality": modality,
                "region": region,
                "description": text.strip(),
                "model": model,
                "generated_on": date.today().isoformat(),
            }
        )
        print(f"{name}: {len(text.split())} words")
    (DEMO_DIR / "analyses.json").write_text(json.dumps(analyses, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
