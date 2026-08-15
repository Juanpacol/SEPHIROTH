"""In-memory vector store — pure-Python dot product over pre-normalized
vectors. At the corpus size this project operates at (tens to low hundreds
of guideline documents) this is trivially fast and avoids adding numpy as a
hard dependency (today it only arrives transitively via imaging libs)."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import ScoredDoc


class InMemoryVectorStore:
    def __init__(self):
        self._vectors: Dict[str, List[float]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        # Insertion order is preserved (dict semantics) so tie-breaking in
        # `search` is deterministic across repeated runs.
        self._order: List[str] = []

    def upsert(self, doc_id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
        if doc_id not in self._vectors:
            self._order.append(doc_id)
        self._vectors[doc_id] = vector
        self._metadata[doc_id] = metadata

    def count(self) -> int:
        return len(self._vectors)

    def search(self, vector: List[float], top_k: int, min_score: float = 0.0) -> List[ScoredDoc]:
        scored = []
        for doc_id in self._order:
            doc_vector = self._vectors[doc_id]
            score = sum(a * b for a, b in zip(vector, doc_vector))
            if score >= min_score:
                scored.append(ScoredDoc(id=doc_id, score=score))
        # Stable sort: ties keep insertion order, so results never flake.
        scored.sort(key=lambda sd: sd.score, reverse=True)
        return scored[:top_k]
