"""FastMCP server exposing multimodal (vision) medical image description.

Uses a local multimodal Ollama model (default llava:7b) via a one-shot
``generate()`` call — unlike the chat/tool-calling loop in
``intelligence/llm/ollama_client.py``, vision description needs no tools,
so the server talks to Ollama directly, matching how other MCP servers
are self-contained.
"""

import base64
from pathlib import Path
from typing import Any, Dict

from fastmcp import FastMCP
from ollama import AsyncClient

mcp = FastMCP(
    name="vision",
    instructions="AI-generated clinical descriptions of medical images via a local vision model.",
)

DESCRIPTION_PROMPT = (
    "You are assisting a radiologist. Describe this medical image in clinical "
    "language: image type/modality if recognizable, anatomical region, notable "
    "structures, and any visible abnormalities or areas warranting closer "
    "review. Be factual — describe only what is visible; do not diagnose. "
    "Keep it under 200 words."
)

READABLE_FORMATS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def _settings():
    from core.config import settings  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    return settings


@mcp.tool
async def describe_medical_image(image_path: str, clinical_focus: str = "") -> Dict[str, Any]:
    """Generate an AI clinical description of a medical image using a local
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

    image_b64 = base64.b64encode(path.read_bytes()).decode()
    prompt = DESCRIPTION_PROMPT
    if clinical_focus:
        prompt += f"\nFocus especially on: {clinical_focus}."

    try:
        client = AsyncClient(host=settings.ollama_host)
        response = await client.generate(
            model=settings.ollama_vision_model,
            prompt=prompt,
            images=[image_b64],
            options={"num_predict": 512},
        )
        description = (response.get("response") or "").strip()
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": (
                f"Vision model '{settings.ollama_vision_model}' failed: {exc}. "
                f"Pull it with: ollama pull {settings.ollama_vision_model}"
            ),
            "description": None,
            "requires_professional_review": True,
        }

    return {
        "status": "ok",
        "description": description,
        "model": settings.ollama_vision_model,
        "clinical_focus": clinical_focus or None,
        "requires_professional_review": True,
    }
