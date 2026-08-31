"""Claim extraction — decomposes a coordinator answer into independently
verifiable assertions.

Today's `citation_guard` audits citation *labels* against tool output; it
cannot tell whether the sentence attached to a citation says what the source
actually says. Decomposing the answer into claims is the prerequisite for
checking that (`verify.py`).
"""

from __future__ import annotations

import uuid
from typing import List

from sephiroth.contracts import Claim, RiskLevel
from sephiroth.models import ModelProvider

CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "originating_agent": {"type": "string"},
                    "risk": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                },
                "required": ["text"],
            },
        }
    },
    "required": ["claims"],
}

SYSTEM_PROMPT = (
    "You decompose a clinical answer into independently verifiable factual "
    "claims. Each claim is a single assertion (a recommendation, a fact, a "
    "value) that can be checked against evidence on its own. Tag each claim "
    "with the specialist section it most closely matches (originating_agent, "
    "e.g. 'evidence', 'drug_safety') and a coarse clinical risk level "
    "(low/medium/high/critical) — high/critical for claims where being wrong "
    "could cause patient harm (dosing, contraindications, diagnosis). Never "
    "invent claims not present in the answer."
)


async def extract_claims(answer: str, client: ModelProvider) -> List[Claim]:
    """One `generate_json` call. Degrades to no claims (never abstains on its
    own failure — an empty claim set leaves `supported_claim_ratio` at 1.0,
    the same as "nothing was asserted")."""
    if not answer.strip():
        return []
    try:
        payload = await client.generate_json(prompt=answer, schema=CLAIMS_SCHEMA, system_prompt=SYSTEM_PROMPT)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []

    claims: List[Claim] = []
    for raw in payload.get("claims", []):
        if not isinstance(raw, dict):
            continue
        text = (raw.get("text") or "").strip()
        if not text:
            continue
        try:
            # Fail-safe, not fail-open: a missing/malformed risk field must
            # not silently exempt the claim from the abstention gate's
            # unsupported-high-risk check (safety/abstention.py).
            risk = RiskLevel(raw.get("risk", "high"))
        except ValueError:
            risk = RiskLevel.HIGH
        claims.append(
            Claim(
                id=uuid.uuid4().hex,
                text=text,
                originating_agent=raw.get("originating_agent") or "",
                risk=risk,
            )
        )
    return claims


__all__ = ["CLAIMS_SCHEMA", "extract_claims"]
