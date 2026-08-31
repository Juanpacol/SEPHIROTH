"""Direct medical tool endpoints (NLP extraction, imaging analysis).

Every endpoint requires authentication (`docs/specs/SPEC-002-tool-runtime.md`
DEBT-004): these call tools directly with attacker-controlled arguments — an
unauthenticated caller could run image analysis, entity extraction, or drug
interaction checks, or read arbitrary local image files via `/imaging/preview`,
at will. Every other endpoint touching clinical data or tools already requires
auth; this brings these six in line.
"""

import json
import mimetypes
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user
from core.config import settings
from core.db import get_session
from data.schemas import Patient, TimelineEvent, User
from intelligence.mcp.vision_server import (
    _MIME_OVERRIDES,
    DESCRIPTION_MAX_OUTPUT_TOKENS,
    DESCRIPTION_PROMPT,
    MAX_IMAGE_BYTES,
    READABLE_FORMATS,
    detect_modality,
)
from sephiroth.models import LLMUnavailableError, get_llm_client
from sephiroth.tools import get_tool_runtime

router = APIRouter()

# Browser-renderable formats only — this is not a general file-download route.
_PREVIEWABLE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
# System temp dir, not a repo path: this whole imaging flow is explicitly a
# local-first, single-user tool (see preview_image's docstring) — an upload
# just needs *some* real path on disk for analyze/describe/preview to read
# back, the same way a typed-in path always has.
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "sephiroth-imaging-uploads"


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)


@router.post("/nlp/extract")
async def extract_entities(request: ExtractRequest, user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Extract medical entities (diseases, medications, symptoms, procedures)."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute("extract_medical_entities", {"text": request.text})


@router.post("/nlp/summarize")
async def summarize_note(request: ExtractRequest, user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Summarize a clinical note."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute("summarize_clinical_note", {"text": request.text})


class ImagingRequest(BaseModel):
    image_path: str
    modality: str = "xray"
    target: str = ""


@router.post("/imaging/analyze")
async def analyze_image(request: ImagingRequest, user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Analyze a medical image (returns structured findings)."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute(
        "analyze_medical_image",
        {"image_path": request.image_path, "modality": request.modality, "target": request.target},
    )


class DescribeRequest(BaseModel):
    image_path: str
    clinical_focus: str = ""


@router.post("/imaging/describe", summary="Describe a medical image with the local vision model")
async def describe_image(request: DescribeRequest, user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Generate an AI clinical description of a medical image (LLaVA via Ollama)."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute(
        "describe_medical_image",
        {"image_path": request.image_path, "clinical_focus": request.clinical_focus},
    )


@router.post(
    "/imaging/describe/stream",
    summary="Stream a live, token-by-token AI clinical description of a medical image",
)
async def describe_image_stream(
    request: DescribeRequest, user: User = Depends(get_current_user)
) -> StreamingResponse:
    """SSE variant of `/imaging/describe` — emits `chunk` events as the vision
    model samples its response, then one `final` event with the full text.
    Mirrors `/api/agents/consult/stream`'s event-envelope shape so the
    frontend can reuse the same fetch+ReadableStream parsing pattern."""

    async def event_stream():
        if not settings.enable_vision_analysis:
            detail = "Vision analysis is disabled (ENABLE_VISION_ANALYSIS=false)."
            yield f"data: {json.dumps({'event': 'error', 'detail': detail})}\n\n"
            return

        path = Path(request.image_path)
        if not path.exists():
            detail = f"File not found: {request.image_path}"
            yield f"data: {json.dumps({'event': 'error', 'detail': detail})}\n\n"
            return
        if path.suffix.lower() not in READABLE_FORMATS:
            detail = f"Unsupported format '{path.suffix}'."
            yield f"data: {json.dumps({'event': 'error', 'detail': detail})}\n\n"
            return

        image_bytes = path.read_bytes()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            detail = f"Image too large ({len(image_bytes)} bytes, max {MAX_IMAGE_BYTES})."
            yield f"data: {json.dumps({'event': 'error', 'detail': detail})}\n\n"
            return

        mime_type = (
            _MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "image/png"
        )
        prompt = DESCRIPTION_PROMPT
        if request.clinical_focus:
            prompt += f"\nFocus especially on: {request.clinical_focus}."
        model_name = settings.gemini_vision_model or settings.gemini_model

        full_text = []
        try:
            client = get_llm_client()
            async for chunk in client.describe_image_stream(
                image_bytes=image_bytes,
                mime_type=mime_type,
                prompt=prompt,
                max_output_tokens=DESCRIPTION_MAX_OUTPUT_TOKENS,
            ):
                full_text.append(chunk)
                yield f"data: {json.dumps({'event': 'chunk', 'text': chunk})}\n\n"
        except LLMUnavailableError as exc:
            detail = f"Vision model '{model_name}' failed: {exc}. Check GEMINI_API_KEY and quota."
            yield f"data: {json.dumps({'event': 'error', 'detail': detail})}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'error', 'detail': f'Vision model failed: {exc}'})}\n\n"
            return

        final_payload = {"event": "final", "description": "".join(full_text), "model": model_name}
        yield f"data: {json.dumps(final_payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/imaging/detect-modality", summary="Best-effort modality guess, to pre-fill the modality dropdown"
)
async def detect_image_modality(
    request: DescribeRequest, user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """Reuses `DescribeRequest` (only `image_path` matters here) — same
    file-read/validation as `/imaging/describe/stream`. Never errors on a
    readable image; degrades to `{"modality": "unknown"}` if vision is
    unavailable, same posture as `detect_modality` itself."""
    path = Path(request.image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.image_path}")
    if path.suffix.lower() not in READABLE_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{path.suffix}'.")

    image_bytes = path.read_bytes()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"Image too large (max {MAX_IMAGE_BYTES} bytes).")

    mime_type = _MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "image/png"
    return {"modality": await detect_modality(image_bytes, mime_type)}


@router.post("/imaging/upload", summary="Upload an image file for analysis, in place of typing a path")
async def upload_image(file: UploadFile, user: User = Depends(get_current_user)) -> Dict[str, str]:
    """Drag-and-drop replacement for typing a server-side file path — saves
    the uploaded bytes to a scratch directory and returns the resulting
    path, which `analyze_image`/`describe_image`/`preview_image` all
    already accept unchanged. Same extension allow-list as the preview
    route: this is a demo-scope imaging flow, not a general file store."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _PREVIEWABLE_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {ext or 'unknown'}")

    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 20 MB limit")
        chunks.append(chunk)

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = _UPLOAD_DIR / f"{uuid4().hex}{ext}"
    dest.write_bytes(b"".join(chunks))
    return {"path": str(dest)}


@router.get("/imaging/preview", summary="Stream a local image file for the side-by-side viewer")
async def preview_image(path: str, user: User = Depends(get_current_user)) -> FileResponse:
    """Serve a browser-renderable image so the imaging page can show it next to the AI findings.

    Same trust boundary as `describe_medical_image`/`analyze_medical_image` — this is a
    local-first, single-user tool where the caller already names arbitrary local file paths.
    Restricted to image extensions so this can't become a general file-download route.
    """
    file_path = Path(path).expanduser()
    if file_path.suffix.lower() not in _PREVIEWABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only image files can be previewed")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)


# Matches the "[image_path:...] [model:...] description text" convention this
# imaging flow writes into `TimelineEvent.detail` (see analyze/describe above
# and the bulk-generation scripts) — TimelineEvent has no dedicated column
# for it, so the recent-analyses view has to parse it back out.
_IMAGE_PATH_RE = re.compile(r"^\[image_path:([^\]]+)\]\s*(?:\[model:([^\]]+)\]\s*)?(.*)$", re.DOTALL)


@router.get(
    "/imaging/recent", summary="Recently AI-analyzed imaging studies, with preview + description"
)
async def recent_imaging_analyses(
    limit: int = 12,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Powers the Imaging page's "Recent analyses" section — every imaging
    `TimelineEvent`, across all patients, newest first, with the source
    image path (if still readable, for `/imaging/preview`) split out from
    the AI description."""
    stmt = (
        select(TimelineEvent, Patient.name)
        .join(Patient, Patient.id == TimelineEvent.patient_id)
        .where(TimelineEvent.type == "imaging")
        .order_by(TimelineEvent.date.desc(), TimelineEvent.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    results: List[Dict[str, Any]] = []
    for event, patient_name in rows:
        image_path: Optional[str] = None
        model: Optional[str] = None
        description = event.detail

        match = _IMAGE_PATH_RE.match(event.detail)
        if match:
            candidate = match.group(1)
            model = match.group(2)
            description = match.group(3).strip()
            candidate_path = Path(candidate)
            if candidate_path.suffix.lower() in _PREVIEWABLE_EXTENSIONS and candidate_path.is_file():
                image_path = candidate

        results.append(
            {
                "id": event.id,
                "patient_id": event.patient_id,
                "patient_name": patient_name,
                "title": event.title,
                "date": event.date.isoformat(),
                "image_path": image_path,
                "model": model,
                "description": description,
                "ai_generated": event.ai_generated,
            }
        )
    return results


class DrugCheckRequest(BaseModel):
    medications: List[str]


@router.post("/drugs/check")
async def check_interactions(
    request: DrugCheckRequest, user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Screen a medication list for drug-drug interactions."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute("check_drug_interactions", {"medications": request.medications})
