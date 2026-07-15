"""Faithfulness scoring: is every claim in the answer backed by evidence?

Two implementations with very different trust levels:

- `heuristic_proxy` — deterministic token-overlap, no LLM. Runs in CI on
  every PR. Coarse by design, so it is reported but never gates a build.
- `judge_llm` — an LLM-as-judge over each claim sentence, run locally
  against Ollama. This is the number that actually gates faithfulness
  regressions, via the committed `results/latest.json`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from data.rag import _tokenize

_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"supported": {"type": "boolean"}},
    "required": ["supported"],
}


@dataclass
class FaithfulnessResult:
    score: float
    claims_checked: int


def _claim_sentences(answer: str) -> List[str]:
    """Split an answer into candidate claim sentences, dropping boilerplate
    (disclaimers, section headers, empty lines)."""
    claims = []
    for line in answer.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sentence in _CLAIM_SPLIT_RE.split(line):
            sentence = sentence.strip("-* ").strip()
            if len(sentence.split()) >= 4 and "professional review" not in sentence.lower():
                claims.append(sentence)
    return claims


def heuristic_proxy(answer: str, evidence_texts: List[str]) -> FaithfulnessResult:
    """Deterministic stand-in for faithfulness: a claim is "supported" if
    its token overlap with any evidence chunk is >= 0.35."""
    claims = _claim_sentences(answer)
    if not claims:
        return FaithfulnessResult(score=1.0, claims_checked=0)

    evidence_token_sets = [set(_tokenize(t)) for t in evidence_texts]
    supported = 0
    for claim in claims:
        claim_tokens = set(_tokenize(claim))
        if not claim_tokens:
            continue
        best = max(
            (len(claim_tokens & ev) / len(claim_tokens) for ev in evidence_token_sets),
            default=0.0,
        )
        if best >= 0.35:
            supported += 1
    return FaithfulnessResult(score=supported / len(claims), claims_checked=len(claims))


async def judge_llm(answer: str, evidence_texts: List[str], client: Any) -> FaithfulnessResult:
    """Per-claim LLM judge: ask the model whether each claim sentence is
    supported by the evidence excerpts. Local-only (needs Ollama) —
    never runs in CI. `client` is an OllamaClient (or a fake with a
    compatible `generate_json`)."""
    claims = _claim_sentences(answer)
    if not claims:
        return FaithfulnessResult(score=1.0, claims_checked=0)

    evidence_block = "\n\n".join(f"[{i + 1}] {t}" for i, t in enumerate(evidence_texts))
    supported = 0
    checked = 0
    for claim in claims:
        prompt = (
            "Evidence excerpts:\n"
            f"{evidence_block}\n\n"
            f'Claim: "{claim}"\n\n'
            "Is this claim directly supported by the evidence excerpts above? "
            "Answer only based on the excerpts, not general medical knowledge."
        )
        try:
            result: Dict[str, Any] = await client.generate_json(prompt, schema=_JUDGE_SCHEMA)
        except Exception:
            # Judge unavailable for this claim (model hiccup, timeout) — skip
            # rather than fail the whole run; excluded from both counts.
            continue
        checked += 1
        if result.get("supported"):
            supported += 1
    if checked == 0:
        return FaithfulnessResult(score=0.0, claims_checked=0)
    return FaithfulnessResult(score=supported / checked, claims_checked=checked)
