"""Reranking — F-035, part 1.

Maximal Marginal Relevance over token overlap, not embeddings: `RAGPipeline`
must keep working with zero configuration (keyword-only, no network), so a
reranker that requires embeddings would silently degrade to a no-op in that
mode. Token-overlap similarity works identically whether or not an
embedding provider is configured — same "simplest that satisfies the spec"
standard as the rest of this package.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _overlap(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def mmr_rerank(
    candidates: List[Dict[str, Any]], lambda_mult: float = 0.7, top_k: int = 5
) -> List[Dict[str, Any]]:
    """Greedily selects `top_k` candidates trading off `score` (relevance)
    against redundancy with what's already been picked, using Jaccard token
    overlap of each candidate's `content` as the similarity proxy.

    `candidates` must already be sorted by relevance (`RAGPipeline`'s fused
    RRF order) — this only reorders for diversity among near-equally-ranked
    hits, it doesn't independently re-score relevance.
    """
    if len(candidates) <= 1:
        return candidates[:top_k]

    pool = list(candidates)
    token_sets = [_tokens(c.get("content", "")) for c in pool]
    max_score = max((c.get("score", 0.0) for c in pool), default=1.0) or 1.0

    selected: List[int] = []
    remaining = list(range(len(pool)))

    while remaining and len(selected) < top_k:
        best_idx = None
        best_value = float("-inf")
        for i in remaining:
            relevance = pool[i].get("score", 0.0) / max_score
            redundancy = max((_overlap(token_sets[i], token_sets[j]) for j in selected), default=0.0)
            value = lambda_mult * relevance - (1 - lambda_mult) * redundancy
            if value > best_value:
                best_value = value
                best_idx = i
        selected.append(best_idx)
        remaining.remove(best_idx)

    return [pool[i] for i in selected]


__all__ = ["mmr_rerank"]
