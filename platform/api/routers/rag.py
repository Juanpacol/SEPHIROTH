"""Evidence retrieval endpoints — clinical guidelines and PubMed."""

from typing import Any, Dict

from fastapi import APIRouter, Query

from intelligence.mcp import get_registry

router = APIRouter()


@router.get("/search")
async def search_evidence(
    q: str = Query(..., min_length=3, description="Clinical question"),
    top_k: int = Query(5, ge=1, le=20),
) -> Dict[str, Any]:
    """Search indexed clinical guidelines (always returns citations)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("search_clinical_guidelines", {"query": q, "top_k": top_k})


@router.get("/pubmed")
async def search_pubmed(
    q: str = Query(..., min_length=3),
    max_results: int = Query(5, ge=1, le=20),
) -> Dict[str, Any]:
    """Search PubMed for peer-reviewed evidence (requires internet)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("search_pubmed", {"query": q, "max_results": max_results})
