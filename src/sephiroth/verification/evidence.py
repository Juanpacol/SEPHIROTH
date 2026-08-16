"""Evidence harvesting — normalizes tool call results into `EvidenceRecord`s.

Mirrors `citation_guard._harvest`'s recursive traversal of tool results, but
keeps passage *content* when a tool result carries it, not just citation
metadata. `search_clinical_guidelines` (via `RAGPipeline.retrieve()`) returns
real passage `content`; `search_pubmed` returns only title/journal/authors —
no abstract. Claims backed only by PubMed evidence are content-verified more
weakly than claims backed by guidelines — a known limitation, not a bug.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from sephiroth.contracts import Citation, EvidenceRecord, RetrievalMethod, SourceType, ToolCall

_CONTENT_KEYS = ("content", "abstract", "summary", "text", "snippet")


def _content_of(item: dict) -> str:
    for key in _CONTENT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _citation_for(item: dict) -> Citation:
    label = item.get("citation") or item.get("source") or item.get("title") or ""
    url = item.get("url") if isinstance(item.get("url"), str) else None
    return Citation(label=str(label), url=url)


def _source_type_for(item: dict) -> SourceType:
    if item.get("pmid") or item.get("journal"):
        return SourceType.LITERATURE
    return SourceType.GUIDELINE


def _relevance_of(item: dict) -> float:
    score = item.get("score")
    if isinstance(score, (int, float)):
        return max(0.0, min(1.0, float(score)))
    return 0.0


def harvest_evidence(tool_calls: List[ToolCall]) -> List[EvidenceRecord]:
    """Every result-bearing passage from a run's tool calls, normalized."""
    records: List[EvidenceRecord] = []
    for call in tool_calls:
        result = call.result
        items = result.get("results") if isinstance(result, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            records.append(
                EvidenceRecord(
                    id=uuid.uuid4().hex,
                    source=str(item.get("source") or item.get("journal") or call.tool),
                    source_type=_source_type_for(item),
                    retrieval_method=RetrievalMethod.TOOL,
                    relevance=_relevance_of(item),
                    citation=_citation_for(item),
                    originating_agent=call.agent,
                    timestamp=datetime.now(timezone.utc),
                    content=_content_of(item),
                )
            )
    return records


__all__: List[str] = ["harvest_evidence"]
