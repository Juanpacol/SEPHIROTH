"""FastMCP server exposing multimodal (vision) medical image description.

Uses the shared Gemini client's one-shot ``describe_image()`` call — unlike
the chat/tool-calling loop in ``sephiroth/models/gemini.py``, vision
description needs no tools. Sharing the client (rather than talking to the
provider directly) means vision competes for the same rate-limit budget and
retry/backoff logic as the agents.
"""

import mimetypes
from pathlib import Path
from typing import Any, Dict

from fastmcp import FastMCP

from sephiroth.models import LLMUnavailableError, get_llm_client

mcp = FastMCP(
    name="vision",
    instructions="AI-generated clinical descriptions of medical images via a cloud vision model.",
)

DESCRIPTION_PROMPT = (
    "You are assisting a radiologist. Describe this medical image in clinical "
    "language: image type/modality if recognizable, anatomical region, notable "
    "structures, and any visible abnormalities or areas warranting closer "
    "review. Be factual — describe only what is visible; do not diagnose. "
    "Keep it under 200 words."
)

READABLE_FORMATS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
_MIME_OVERRIDES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".bmp": "image/bmp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # Gemini's inline request cap is ~20MB

_MODALITY_PROMPT = (
    "Classify this medical image into exactly one of: xray, ct, mri, ultrasound, "
    "pathology, unknown. Reply with only that single word, nothing else."
)
_KNOWN_MODALITIES = {"xray", "ct", "mri", "ultrasound", "pathology"}


async def detect_modality(image_bytes: bytes, mime_type: str) -> str:
    """Best-effort modality guess to pre-fill the `/imaging` page's dropdown
    — not an `@mcp.tool` since no agent needs to "guess a modality", only a
    UI convenience. Degrades to `"unknown"` (never raises) on any failure,
    same posture as `describe_medical_image`'s own `LLMUnavailableError`
    handling, so a flaky vision call never blocks the upload flow — the
    clinician can always pick the modality by hand regardless."""
    try:
        client = get_llm_client()
        raw = await client.describe_image(
            image_bytes=image_bytes, mime_type=mime_type, prompt=_MODALITY_PROMPT, max_output_tokens=8
        )
    except LLMUnavailableError:
        return "unknown"
    guess = raw.strip().lower().strip(".")
    return guess if guess in _KNOWN_MODALITIES else "unknown"


def _settings():
    from core.config import settings  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    return settings


@mcp.tool
async def describe_medical_image(image_path: str, clinical_focus: str = "") -> Dict[str, Any]:
    """Generate an AI clinical description of a medical image using a cloud
    vision model. Optional `clinical_focus` narrows the description (e.g.
    'left lung', 'bone density'). Use when an image is provided and you need
    to know what it shows before reasoning about it."""
    try:
        settings = _settings()
        enabled = settings.enable_vision_analysis
    except Exception:
        return {"status": "unavailable", "message": "Configuration not available."}

    if not enabled:
        return {
            "status": "unavailable",
            "message": "Vision analysis is disabled (ENABLE_VISION_ANALYSIS=false).",
            "description": None,
            "requires_professional_review": True,
        }

    path = Path(image_path)
    if not path.exists():
        return {"error": f"File not found: {image_path}"}
    if path.suffix.lower() not in READABLE_FORMATS:
        return {
            "error": (
                f"Unsupported format '{path.suffix}'. The vision model reads rendered "
                f"images ({', '.join(sorted(READABLE_FORMATS))}); convert DICOM/NIfTI "
                "slices to PNG first."
            )
        }

    image_bytes = path.read_bytes()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return {
            "error": f"Image too large ({len(image_bytes)} bytes, max {MAX_IMAGE_BYTES}) for inline analysis."
        }

    mime_type = _MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "image/png"
    prompt = DESCRIPTION_PROMPT
    if clinical_focus:
        prompt += f"\nFocus especially on: {clinical_focus}."

    model_name = settings.gemini_vision_model or settings.gemini_model
    try:
        client = get_llm_client()
        description = await client.describe_image(image_bytes=image_bytes, mime_type=mime_type, prompt=prompt)
    except LLMUnavailableError as exc:
        return {
            "status": "unavailable",
            "message": f"Vision model '{model_name}' failed: {exc}. Check GEMINI_API_KEY and quota.",
            "description": None,
            "requires_professional_review": True,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"Vision model '{model_name}' failed: {exc}. Check GEMINI_API_KEY and quota.",
            "description": None,
            "requires_professional_review": True,
        }

    return {
        "status": "ok",
        "description": description,
        "model": model_name,
        "clinical_focus": clinical_focus or None,
        "requires_professional_review": True,
    }
