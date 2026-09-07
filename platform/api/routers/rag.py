"""Evidence retrieval endpoints — clinical guidelines and PubMed.

Both endpoints require authentication (`docs/specs/SPEC-002-tool-runtime.md`
DEBT-004): `search_pubmed` makes a real outbound network call per request, so
an unauthenticated endpoint is also an open door to consuming that quota.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.deps import get_current_user
from data.schemas import User
from intelligence.mcp.rag_server import list_evidence_by_category, list_evidence_categories
from sephiroth.tools import get_tool_runtime

router = APIRouter()

# Display label for each category slug used in data/rag/__init__.py's
# SEED_GUIDELINES metadata — the one place that mapping is spelled out, so
# adding a new category later means adding one line here, not touching the
# frontend. Any slug not listed here (e.g. from a future added_document())
# falls back to a title-cased version of the slug itself.
_CATEGORY_LABELS = {
    "cardiovascular": "Cardiovascular",
    "endocrinology": "Endocrinology",
    "nephrology": "Nephrology",
    "pulmonology": "Pulmonology",
    "infectious_disease": "Infectious Disease",
    "critical_care": "Critical Care",
    "screening": "Cancer Screening",
    "neurology": "Neurology",
    "rheumatology": "Rheumatology",
    "obstetrics": "Obstetrics",
    "pediatrics": "Pediatrics",
    "psychiatry": "Psychiatry",
}


@router.get("/categories", summary="Browse the evidence corpus by clinical category")
async def evidence_categories(user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    counts = list_evidence_categories()
    categories = [
        {"slug": slug, "label": _CATEGORY_LABELS.get(slug, slug.replace("_", " ").title()), "count": count}
        for slug, count in counts.items()
    ]
    categories.sort(key=lambda c: c["label"])
    return categories


@router.get("/categories/{category}", summary="Every guideline excerpt in one category")
async def evidence_by_category(category: str, user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    items = list_evidence_by_category(category)
    if not items:
        raise HTTPException(status_code=404, detail=f"No evidence found for category '{category}'")
    return items


@router.get("/search")
async def search_evidence(
    q: str = Query(..., min_length=3, description="Clinical question"),
    top_k: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Search indexed clinical guidelines (always returns citations)."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute("search_clinical_guidelines", {"query": q, "top_k": top_k})


@router.get("/pubmed")
async def search_pubmed(
    q: str = Query(..., min_length=3),
    max_results: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Search PubMed for peer-reviewed evidence (requires internet)."""
    registry = get_tool_runtime()
    await registry.load()
    return await registry.execute("search_pubmed", {"query": q, "max_results": max_results})
