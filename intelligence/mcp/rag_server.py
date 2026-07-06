"""FastMCP server exposing medical evidence retrieval (RAG + PubMed)."""

from typing import Any, Dict

import httpx
from fastmcp import FastMCP

from data.rag import RAGPipeline

mcp = FastMCP(
    name="medical-evidence",
    instructions="Evidence retrieval from clinical guidelines and PubMed. Always cite sources.",
)

_pipeline = RAGPipeline()

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


@mcp.tool
def search_clinical_guidelines(query: str, top_k: int = 5) -> Dict[str, Any]:
    """Search indexed clinical practice guidelines for evidence relevant to a
    clinical question. Returns excerpts with mandatory citations. Use this
    FIRST for treatment/diagnosis questions."""
    results = _pipeline.retrieve(query, top_k=top_k)
    return {
        "query": query,
        "results": results,
        "disclaimer": "Evidence excerpts for professional review; not a diagnosis.",
    }


@mcp.tool
async def search_pubmed(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search PubMed for peer-reviewed articles matching a clinical query.
    Returns titles, authors, journals, years, and PMIDs (citable). Requires
    internet access; falls back gracefully when offline."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            search = await client.get(
                PUBMED_ESEARCH,
                params={"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"},
            )
            ids = search.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return {"query": query, "results": [], "note": "No PubMed matches."}

            summary = await client.get(
                PUBMED_ESUMMARY,
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            )
            payload = summary.json().get("result", {})
            results = []
            for pmid in ids:
                item = payload.get(pmid, {})
                results.append(
                    {
                        "pmid": pmid,
                        "title": item.get("title", ""),
                        "journal": item.get("fulljournalname", ""),
                        "year": (item.get("pubdate", "") or "")[:4],
                        "authors": [a.get("name", "") for a in item.get("authors", [])[:3]],
                        "citation": f"PMID:{pmid}",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    }
                )
            return {"query": query, "results": results}
    except Exception as exc:
        return {
            "query": query,
            "results": [],
            "error": f"PubMed unreachable ({exc}); use search_clinical_guidelines instead.",
        }
