"""Direct medical tool endpoints (NLP extraction, imaging analysis)."""

import mimetypes
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from intelligence.mcp import get_registry

router = APIRouter()

# Browser-renderable formats only — this is not a general file-download route.
_PREVIEWABLE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)


@router.post("/nlp/extract")
async def extract_entities(request: ExtractRequest) -> Dict[str, Any]:
    """Extract medical entities (diseases, medications, symptoms, procedures)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("extract_medical_entities", {"text": request.text})


@router.post("/nlp/summarize")
async def summarize_note(request: ExtractRequest) -> Dict[str, Any]:
    """Summarize a clinical note."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("summarize_clinical_note", {"text": request.text})


class ImagingRequest(BaseModel):
    image_path: str
    modality: str = "xray"
    target: str = ""


@router.post("/imaging/analyze")
async def analyze_image(request: ImagingRequest) -> Dict[str, Any]:
    """Analyze a medical image (returns structured findings)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute(
        "analyze_medical_image",
        {"image_path": request.image_path, "modality": request.modality, "target": request.target},
    )


class DescribeRequest(BaseModel):
    image_path: str
    clinical_focus: str = ""


@router.post("/imaging/describe", summary="Describe a medical image with the local vision model")
async def describe_image(request: DescribeRequest) -> Dict[str, Any]:
    """Generate an AI clinical description of a medical image (LLaVA via Ollama)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute(
        "describe_medical_image",
        {"image_path": request.image_path, "clinical_focus": request.clinical_focus},
    )


@router.get("/imaging/preview", summary="Stream a local image file for the side-by-side viewer")
async def preview_image(path: str) -> FileResponse:
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
async def check_interactions(request: DrugCheckRequest) -> Dict[str, Any]:
    """Screen a medication list for drug-drug interactions."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("check_drug_interactions", {"medications": request.medications})
