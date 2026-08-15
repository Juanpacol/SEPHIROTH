"""Vector store protocol for dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, runtime_checkable


@dataclass
class ScoredDoc:
    id: str
    score: float


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, doc_id: str, vector: List[float], metadata: Dict[str, Any]) -> None: ...

    def search(self, vector: List[float], top_k: int, min_score: float = 0.0) -> List[ScoredDoc]:
        """Return the top_k nearest documents by cosine similarity, excluding
        any below `min_score`. Assumes stored and query vectors are unit-norm
        (cosine similarity == dot product)."""
        ...

    def count(self) -> int: ...
