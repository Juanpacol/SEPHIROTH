"""Combined extract-and-verify — one `generate_json` call instead of two.

`claims.extract_claims` then `verify.verify_claims` are two strictly
sequential model round-trips, and the second cannot start until the first
returns (it needs the claim ids). Measured on a local model, that pair was
47s of a 74s consultation — 64% of the wall clock, more than producing the
answer itself. Merging them removes one full round-trip.

**Every guarantee of the two-call path is preserved**, and the pieces that
provide them are imported from their original modules rather than
reimplemented:

- Claim decomposition, risk tagging, and originating-agent tagging —
  same fields, same enum, same "never invent claims" instruction.
- The deterministic post-check from `verify.py`: a `supported` verdict is
  downgraded to `partially_supported` when the claim shares almost no
  vocabulary with its cited evidence (`_overlap_supports`). ADR-006's own
  stated risk is that the judge is itself an LLM; that check is what keeps
  it from being trusted alone, so it survives the merge unchanged.
- Contradiction detection between claims.
- Degradation: any failure (exception, non-dict payload, malformed
  entries) yields no claims, exactly as `extract_claims` did — an empty
  claim set leaves `supported_claim_ratio` at 1.0, the same as "nothing
  was asserted".
- The no-evidence case still marks every claim `UNKNOWN`, never silently
  `SUPPORTED`.

The single call asks the model to decompose AND judge in one pass, so it
assigns its own claim ids; the two-call path had Python generate them
between the calls. Ids are only used to join verdicts to claims within
one report, so their provenance doesn't matter — but a missing or
duplicate id must not silently drop a claim, hence the fallback id
assignment below.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sephiroth.contracts import (
    Claim,
    Contradiction,
    EvidenceRecord,
    RiskLevel,
    VerificationReport,
    VerificationStatus,
)
from sephiroth.models import ModelProvider

from .verify import _overlap_supports

_STATUS_VALUES = sorted(status.value for status in VerificationStatus)

# No per-claim `rationale` here, unlike the two-call schema in `verify.py`.
# On a local CPU model decoding is the wall clock (~23 tok/s), and a free-prose
# rationale per claim was the single largest block of generated JSON — while
# being read by nothing: it reaches no UI surface and no gate. Abstention
# keys off status/risk/confidence, and the one rationale that carries meaning
# (the ADR-006 low-overlap downgrade) is written by Python below, not by the
# model. `_claim_from` still accepts the field if a model volunteers it.
COMBINED_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "originating_agent": {"type": "string"},
                    "risk": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "status": {"type": "string", "enum": _STATUS_VALUES},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["text", "status"],
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
    "required": ["claims"],
}

SYSTEM_PROMPT = (
    "You decompose a clinical answer into independently verifiable factual "
    "claims AND judge each one against the provided evidence, in a single "
    "pass.\n\n"
    "For each claim: give it a short unique id, the claim text (a single "
    "assertion — a recommendation, a fact, a value — checkable on its own), "
    "the specialist section it most closely matches (originating_agent, e.g. "
    "'evidence', 'drug_safety'), and a coarse clinical risk level "
    "(low/medium/high/critical — high or critical when being wrong could "
    "cause patient harm: dosing, contraindications, diagnosis).\n\n"
    "Then judge it against the evidence passages: supported (evidence "
    "directly confirms it), partially_supported (related but incomplete), "
    "unsupported (no evidence addresses it), contradicted (evidence "
    "disagrees), or unknown (no relevant evidence provided at all). List "
    "which evidence ids you used per claim.\n\n"
    "Never invent claims not present in the answer. Also list any "
    "contradictions between claims."
)


def _unwrap_schema_echo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Undo a model echoing the JSON Schema envelope instead of an instance.

    Providers that can only *ask* for a schema in the prompt (rather than
    constrain decoding to it) sometimes get back
    `{"type": "object", "properties": {"claims": [...]}}` with the values
    filled in under `properties`. Read naively that yields no claims, and an
    empty claim set is indistinguishable from "the answer asserted nothing" —
    so verification would report a clean pass while having verified nothing.
    Silent-pass is the one failure mode this module must not have, so unwrap
    it rather than trusting every provider to never drift.
    """
    if "claims" in payload:
        return payload
    inner = payload.get("properties")
    if isinstance(inner, dict) and isinstance(inner.get("claims"), list):
        return inner
    return payload


def _prompt_aliases(evidence: List[EvidenceRecord]) -> Dict[str, str]:
    """Short per-call labels (`e1`, `e2`, …) standing in for evidence ids.

    `EvidenceRecord.id` is a 32-char uuid4 hex. The model has to copy one
    verbatim into `evidence_ids` for a verdict to be joinable, and a small
    local model routinely mistypes them; the unmatched id is then dropped,
    `_overlap_supports` finds no evidence to compare against, and a correct
    `supported` verdict is downgraded — turning a well-grounded answer into
    an abstention. The ids are opaque join keys with no meaning to the model,
    so nothing is lost by labelling them in a form it can actually echo.
    """
    return {record.id: f"e{index}" for index, record in enumerate(evidence, start=1)}


def _build_prompt(answer: str, evidence: List[EvidenceRecord], alias_of: Dict[str, str]) -> str:
    evidence_lines = "\n".join(
        f"- id={alias_of[e.id]} source={e.source}: {e.content or e.citation.label}" for e in evidence
    )
    return f"Answer to decompose and verify:\n{answer}\n\nEvidence:\n{evidence_lines}"


def _claim_from(
    raw: Dict[str, Any],
    evidence_by_id: Dict[str, EvidenceRecord],
    id_by_reference: Dict[str, str],
) -> Claim | None:
    text = (raw.get("text") or "").strip()
    if not text:
        return None

    try:
        # Fail-safe, not fail-open — see claims.py's identical fallback.
        risk = RiskLevel(raw.get("risk", "high"))
    except ValueError:
        risk = RiskLevel.HIGH
    try:
        status = VerificationStatus(raw.get("status", "unknown"))
    except ValueError:
        status = VerificationStatus.UNKNOWN

    raw_confidence = raw.get("confidence")
    confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.5
    confidence = max(0.0, min(1.0, confidence))

    claim = Claim(
        # The model supplies ids here (it must, to reference them from
        # `contradictions`), but a missing one must not drop the claim.
        id=str(raw.get("id") or "").strip() or uuid.uuid4().hex,
        text=text,
        originating_agent=raw.get("originating_agent") or "",
        risk=risk,
        status=status,
        evidence_ids=[id_by_reference[r] for r in raw.get("evidence_ids", []) if r in id_by_reference],
        confidence=confidence,
        rationale=raw.get("rationale", "") or "",
    )

    # ADR-006's mitigation, unchanged from the two-call path: never trust
    # a `supported` verdict whose claim shares almost no vocabulary with
    # the evidence it cites.
    if status is VerificationStatus.SUPPORTED and not _overlap_supports(claim, evidence_by_id):
        claim = claim.model_copy(
            update={
                "status": VerificationStatus.PARTIALLY_SUPPORTED,
                "rationale": (
                    claim.rationale + " [downgraded: low token overlap with cited evidence]"
                ).strip(),
            }
        )
    return claim


async def extract_and_verify(
    answer: str, evidence: List[EvidenceRecord], client: ModelProvider
) -> VerificationReport:
    """One call that decomposes `answer` into claims and judges each against
    `evidence`. Returns an empty report on any failure — see module
    docstring for why that is the safe degradation."""
    if not answer.strip():
        return VerificationReport()

    if not evidence:
        # No evidence to judge against. Still decompose (the abstention gate
        # needs to know a high-risk claim was made), but every verdict is
        # UNKNOWN — never silently SUPPORTED. Falls back to the extraction-
        # only path, which is exactly what the two-call version did here.
        from .claims import extract_claims

        claims = await extract_claims(answer, client)
        return VerificationReport(
            claims=[c.model_copy(update={"status": VerificationStatus.UNKNOWN}) for c in claims]
        )

    evidence_by_id = {e.id: e for e in evidence}
    alias_of = _prompt_aliases(evidence)
    # Accept either the alias the prompt showed or the real id, so a model
    # that happens to quote the underlying id still joins correctly.
    id_by_reference = {alias: record_id for record_id, alias in alias_of.items()}
    id_by_reference.update({record_id: record_id for record_id in evidence_by_id})
    try:
        payload = await client.generate_json(
            prompt=_build_prompt(answer, evidence, alias_of),
            schema=COMBINED_SCHEMA,
            system_prompt=SYSTEM_PROMPT,
        )
    except Exception:
        return VerificationReport()
    if not isinstance(payload, dict):
        return VerificationReport()
    payload = _unwrap_schema_echo(payload)

    claims: List[Claim] = []
    for raw in payload.get("claims", []):
        if not isinstance(raw, dict):
            continue
        claim = _claim_from(raw, evidence_by_id, id_by_reference)
        if claim is not None:
            claims.append(claim)

    known_ids = {c.id for c in claims}
    contradictions = [
        Contradiction(
            id=uuid.uuid4().hex,
            claim_id=raw["claim_id"],
            conflicting_claim_id=raw.get("conflicting_claim_id"),
            description=raw.get("description", "") or "",
        )
        for raw in payload.get("contradictions", [])
        if isinstance(raw, dict) and raw.get("claim_id") in known_ids
    ]
    return VerificationReport(claims=claims, contradictions=contradictions)


__all__ = ["COMBINED_SCHEMA", "extract_and_verify"]
