"""Evidence retrieval endpoints — clinical guidelines and PubMed.

Both endpoints require authentication (`docs/specs/SPEC-002-tool-runtime.md`
DEBT-004): `search_pubmed` makes a real outbound network call per request, so
an unauthenticated endpoint is also an open door to consuming that quota.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from auth.deps import get_current_user
from data.schemas import User
from intelligence.mcp import get_registry

router = APIRouter()


@router.get("/search")
async def search_evidence(
    q: str = Query(..., min_length=3, description="Clinical question"),
    top_k: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Search indexed clinical guidelines (always returns citations)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("search_clinical_guidelines", {"query": q, "top_k": top_k})


@router.get("/pubmed")
async def search_pubmed(
    q: str = Query(..., min_length=3),
    max_results: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Search PubMed for peer-reviewed evidence (requires internet)."""
    registry = get_registry()
    await registry.load()
    return await registry.execute("search_pubmed", {"query": q, "max_results": max_results})
