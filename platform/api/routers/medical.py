"""Direct medical tool endpoints (NLP extraction, imaging analysis).

Every endpoint requires authentication (`docs/specs/SPEC-002-tool-runtime.md`
DEBT-004): these call tools directly with attacker-controlled arguments — an
unauthenticated caller could run image analysis, entity extraction, or drug
interaction checks, or read arbitrary local image files via `/imaging/preview`,
at will. Every other endpoint touching clinical data or tools already requires
auth; this brings these six in line.
"""

import mimetypes
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth.deps import get_current_user
from data.schemas import User
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
