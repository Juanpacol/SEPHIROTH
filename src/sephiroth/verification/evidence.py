"""Evidence harvesting — normalizes tool call results into `EvidenceRecord`s.

Mirrors `citation_guard._harvest`'s recursive traversal of tool results, but
keeps passage *content* when a tool result carries it, not just citation
metadata. `search_clinical_guidelines` (via `RAGPipeline.retrieve()`) returns
real passage `content`; `search_pubmed` returns only title/journal/authors —
no abstract. Claims backed only by PubMed evidence are content-verified more
weakly than claims backed by guidelines — a known limitation, not a bug.

`check_drug_interactions` returns its rows under `interactions`, not
`results`. Reading only `results` left every drug-safety consultation with
zero evidence, so `extract_and_verify` took its no-evidence branch and marked
each claim UNKNOWN; whether the run then answered or abstained came down to
whether claim extraction happened to return zero claims that time. Same
question, same code, different outcome per run.

`harvest_observations` (SPEC-004 1.2.0, ADR-018) is the same idea applied to
a perception tool's own output (vision's `description`, imaging's
`findings`) — kept as a separate function, never merged into
`harvest_evidence`'s list, so an answer can never cite its own tool's output
as independent corroboration of itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from sephiroth.contracts import Citation, EvidenceRecord, RetrievalMethod, SourceType, ToolCall

_CONTENT_KEYS = ("content", "abstract", "summary", "text", "snippet")

# Which list-valued keys of a tool result hold citable evidence. Deliberately
# an allowlist rather than citation_guard's recursive sweep: imaging's
# `findings` and vision's `description` are the model's *own* output, and
# admitting those as evidence would let an answer verify itself.
_EVIDENCE_LIST_KEYS = ("results", "interactions")

# `check_drug_interactions` hand-curated rows carry no provenance field of
# their own (DDInter-sourced rows do, and keep theirs).
_DRUG_TABLE_SOURCE = "Curated drug-interaction table"


def _as_evidence_item(item: dict, key: str) -> dict:
    """Reshape a result entry into the citation/content shape the record
    builders expect.

    Only `interactions` needs this: its fields (`pair`, `severity`, `effect`,
    `recommendation`) match no `_CONTENT_KEYS` and no citation key, so the
    record would otherwise carry empty `content` — and `_overlap_supports`
    skips content-less evidence, which downgrades every claim it grounds.
    """
    if key != "interactions":
        return item

    pair = item.get("pair")
    pair_text = " + ".join(str(drug) for drug in pair) if isinstance(pair, list) else ""
    severity = str(item.get("severity") or "")
    parts = [
        f"{pair_text}: {severity} interaction".strip() if severity else pair_text,
        str(item.get("effect") or ""),
        str(item.get("recommendation") or ""),
    ]
    return {
        **item,
        "content": " ".join(part for part in parts if part),
        "source": item.get("source") or _DRUG_TABLE_SOURCE,
    }


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
        if not isinstance(result, dict):
            continue
        for key in _EVIDENCE_LIST_KEYS:
            items = result.get(key)
            if not isinstance(items, list):
                continue
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                item = _as_evidence_item(raw, key)
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


#: Perception tools whose own output `harvest_observations` may turn into a
#: TOOL_OUTPUT record, and how to pull the observed content out of each
#: one's success shape. Deliberately separate from `_EVIDENCE_LIST_KEYS` —
#: see ADR-018: faithfulness to a tool's own output is checkable, but it
#: must never become evidence an answer can cite as independent
#: corroboration of itself.
_PERCEPTION_TOOL_FIELDS = {
    "describe_medical_image": "description",
    "analyze_medical_image": "findings",
}


def _observation_content(tool: str, field: str, result: dict) -> str:
    value = result.get(field)
    if tool == "analyze_medical_image":
        if not isinstance(value, list) or not value:
            return ""
        return "; ".join(
            f"{item.get('label', '')} ({item.get('probability', '')})"
            for item in value
            if isinstance(item, dict)
        )
    return value if isinstance(value, str) else ""


def harvest_observations(tool_calls: List[ToolCall]) -> List[EvidenceRecord]:
    """A perception tool's own successful output, kept separate from
    `harvest_evidence` (ADR-018) — never admitted as evidence an answer can
    cite as independent corroboration, but faithfully reporting it is still
    a checkable claim (`sephiroth.verification.combined`/`verify`'s OBSERVED
    promotion).

    Degraded results (`status: "unavailable"`/`"model_not_configured"`, an
    `{"error": ...}` shape, or an empty description/findings list) yield
    nothing — the same fail-open posture as `harvest_evidence`."""
    records: List[EvidenceRecord] = []
    for call in tool_calls:
        field = _PERCEPTION_TOOL_FIELDS.get(call.tool)
        if field is None:
            continue
        result = call.result
        if not isinstance(result, dict) or result.get("status") != "ok":
            continue
        content = _observation_content(call.tool, field, result)
        if not content:
            continue
        records.append(
            EvidenceRecord(
                id=uuid.uuid4().hex,
                source=str(result.get("model") or call.tool),
                source_type=SourceType.TOOL_OUTPUT,
                retrieval_method=RetrievalMethod.TOOL,
                relevance=1.0,
                citation=Citation(label="AI visual description"),
                originating_agent=call.agent,
                timestamp=datetime.now(timezone.utc),
                content=content,
            )
        )
    return records


__all__: List[str] = ["harvest_evidence", "harvest_observations"]
