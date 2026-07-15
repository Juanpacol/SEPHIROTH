"""Pure, deterministic metrics for the RAG evaluation harness.

No I/O, no LLM calls — every function here takes already-computed inputs
(retrieved doc ids, transcripts) and returns a number or a small report.
This is what makes `--mode ci` possible without Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from intelligence.agents.citation_guard import audit
from intelligence.evaluation.dataset import GoldenCase


def recall_at_k(
    cases: List[GoldenCase],
    retrieved_ids_by_case: Dict[str, List[str]],
    k: int,
) -> float:
    """Mean |top_k retrieved ∩ relevant| / |relevant| over cases that have
    at least one relevant document. Adversarial (no-relevant-doc) cases are
    excluded from the denominator — there's nothing to recall."""
    scores = []
    for case in cases:
        if not case.relevant_doc_ids:
            continue
        retrieved = retrieved_ids_by_case.get(case.id, [])[:k]
        hit = len(set(retrieved) & set(case.relevant_doc_ids))
        scores.append(hit / len(case.relevant_doc_ids))
    return sum(scores) / len(scores) if scores else 0.0


def mrr(cases: List[GoldenCase], retrieved_ids_by_case: Dict[str, List[str]]) -> float:
    """Mean reciprocal rank of the first relevant document in the retrieved
    list (0 if none of the relevant docs appear)."""
    scores = []
    for case in cases:
        if not case.relevant_doc_ids:
            continue
        retrieved = retrieved_ids_by_case.get(case.id, [])
        rank = next(
            (i + 1 for i, doc_id in enumerate(retrieved) if doc_id in case.relevant_doc_ids),
            None,
        )
        scores.append(1.0 / rank if rank else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


@dataclass
class CitationMetrics:
    precision: float
    verified: int
    fabricated: int
    per_case: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "precision": round(self.precision, 4),
            "verified": self.verified,
            "fabricated": self.fabricated,
            "per_case": self.per_case,
        }


def citation_metrics(transcripts: List[Dict[str, Any]]) -> CitationMetrics:
    """Citation Precision aggregated across recorded transcripts, computed
    by replaying the existing Citation Guard `audit()` over each answer +
    its recorded tool_calls."""
    total_verified = 0
    total_fabricated = 0
    per_case = []
    for t in transcripts:
        report = audit(t["answer"], t.get("tool_calls", []))
        total_verified += len(report.verified)
        total_fabricated += len(report.fabricated)
        per_case.append(
            {
                "id": t["case_id"],
                "verified": report.verified,
                "fabricated": report.fabricated,
            }
        )
    denom = total_verified + total_fabricated
    precision = total_verified / denom if denom else 1.0
    return CitationMetrics(
        precision=precision,
        verified=total_verified,
        fabricated=total_fabricated,
        per_case=per_case,
    )


def citation_recall(cases: List[GoldenCase], transcripts_by_case: Dict[str, Dict[str, Any]]) -> float:
    """Fraction of `expected_citation_substrings` that actually appear
    (case-insensitive) in the recorded answer — catches an agent that
    retrieves correctly but forgets to cite."""
    scores = []
    for case in cases:
        if not case.expected_citation_substrings:
            continue
        transcript = transcripts_by_case.get(case.id)
        answer = (transcript or {}).get("answer", "").lower()
        hits = sum(1 for s in case.expected_citation_substrings if s.lower() in answer)
        scores.append(hits / len(case.expected_citation_substrings))
    return sum(scores) / len(scores) if scores else 0.0


def fabrication_rate_on_adversarial(
    cases: List[GoldenCase], transcripts_by_case: Dict[str, Dict[str, Any]]
) -> float:
    """Fraction of adversarial (no-evidence) cases where the answer still
    contains a fabricated citation. Should be 0 — this is the Citation
    Guard's core job."""
    adversarial = [c for c in cases if c.expects_abstention]
    if not adversarial:
        return 0.0
    fabricated_count = 0
    for case in adversarial:
        transcript = transcripts_by_case.get(case.id)
        if not transcript:
            continue
        report = audit(transcript["answer"], transcript.get("tool_calls", []))
        if report.fabricated:
            fabricated_count += 1
    return fabricated_count / len(adversarial)
