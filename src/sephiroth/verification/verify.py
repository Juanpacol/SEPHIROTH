"""Claim verification — one batched LLM-judge call per consultation, not one
per claim (ADR-006: the judge call is the dominant cost of the reliability
mechanisms; batching keeps it O(1) round-trips instead of O(n_claims)).

ADR-006's own risk ("the verifier is itself an LLM and can be wrong") is
mitigated with a cheap deterministic check: a `supported` verdict is
downgraded to `partially_supported` when the claim and its cited evidence
share almost no vocabulary — never trust the judge alone.
"""

from __future__ import annotations

import uuid
from typing import Dict, List

from sephiroth.contracts import Claim, Contradiction, EvidenceRecord, VerificationReport, VerificationStatus
from sephiroth.models import ModelProvider

_STATUS_VALUES = sorted(status.value for status in VerificationStatus)

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "status": {"type": "string", "enum": _STATUS_VALUES},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["claim_id", "status"],
            },
        },
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "conflicting_claim_id": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["claim_id"],
            },
        },
    },
    "required": ["verdicts"],
}

SYSTEM_PROMPT = (
    "You are a clinical claim verifier. For each claim, decide whether the "
    "provided evidence passages support it: supported (evidence directly "
    "confirms it), partially_supported (evidence is related but incomplete), "
    "unsupported (no evidence addresses it), contradicted (evidence disagrees "
    "with it), or unknown (no relevant evidence was provided at all). Cite "
    "which evidence ids you used per claim. Also list any contradictions "
    "between claims."
)

_MIN_OVERLAP_TOKENS = 2


def _tokens(text: str) -> set:
    return {t for t in text.lower().split() if len(t) > 2}


def _overlap_supports(claim: Claim, evidence_by_id: Dict[str, EvidenceRecord]) -> bool:
    claim_tokens = _tokens(claim.text)
    for evidence_id in claim.evidence_ids:
        record = evidence_by_id.get(evidence_id)
        if record is None or not record.content:
            continue
        if len(claim_tokens & _tokens(record.content)) >= _MIN_OVERLAP_TOKENS:
            return True
    return False


def _build_prompt(claims: List[Claim], evidence: List[EvidenceRecord]) -> str:
    claim_lines = "\n".join(f"- id={c.id} risk={c.risk.value}: {c.text}" for c in claims)
    evidence_lines = "\n".join(
        f"- id={e.id} source={e.source}: {e.content or e.citation.label}" for e in evidence
    )
    return f"Claims:\n{claim_lines}\n\nEvidence:\n{evidence_lines}"


async def verify_claims(
    claims: List[Claim], evidence: List[EvidenceRecord], client: ModelProvider
) -> VerificationReport:
    if not claims:
        return VerificationReport()
    if not evidence:
        # Nothing to check against — every claim is UNKNOWN, not silently SUPPORTED.
        return VerificationReport(
            claims=[c.model_copy(update={"status": VerificationStatus.UNKNOWN}) for c in claims]
        )

    evidence_by_id = {e.id: e for e in evidence}
    try:
        payload = await client.generate_json(
            prompt=_build_prompt(claims, evidence), schema=VERIFY_SCHEMA, system_prompt=SYSTEM_PROMPT
        )
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    verdicts = {v.get("claim_id"): v for v in payload.get("verdicts", []) if isinstance(v, dict)}

    verified_claims: List[Claim] = []
    for claim in claims:
        verdict = verdicts.get(claim.id)
        if verdict is None:
            verified_claims.append(claim.model_copy(update={"status": VerificationStatus.UNKNOWN}))
            continue

        try:
            status = VerificationStatus(verdict.get("status", "unknown"))
        except ValueError:
            status = VerificationStatus.UNKNOWN

        evidence_ids = [eid for eid in verdict.get("evidence_ids", []) if eid in evidence_by_id]
        raw_confidence = verdict.get("confidence")
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.5
        confidence = max(0.0, min(1.0, confidence))

        updated = claim.model_copy(
            update={
                "status": status,
                "evidence_ids": evidence_ids,
                "confidence": confidence,
                "rationale": verdict.get("rationale", "") or "",
            }
        )
        if status is VerificationStatus.SUPPORTED and not _overlap_supports(updated, evidence_by_id):
            updated = updated.model_copy(
                update={
                    "status": VerificationStatus.PARTIALLY_SUPPORTED,
                    "rationale": (
                        updated.rationale + " [downgraded: low token overlap with cited evidence]"
                    ).strip(),
                }
            )
        verified_claims.append(updated)

    contradictions = [
        Contradiction(
            id=uuid.uuid4().hex,
            claim_id=raw["claim_id"],
            conflicting_claim_id=raw.get("conflicting_claim_id"),
            description=raw.get("description", "") or "",
        )
        for raw in payload.get("contradictions", [])
        if isinstance(raw, dict) and raw.get("claim_id")
    ]
    return VerificationReport(claims=verified_claims, contradictions=contradictions)


__all__ = ["VERIFY_SCHEMA", "verify_claims"]
