"""Embedding provider protocol — synchronous, matching `RAGPipeline.retrieve()`
and the `search_clinical_guidelines` MCP tool (both sync). Making this async
would ripple into the MCP tool contract and the eval runner for no benefit
at this corpus size (tens of documents)."""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable


class EmbeddingUnavailable(RuntimeError):
    """Raised when no embedding vector can be produced (no API key, cache
    miss with no live provider, network failure). Callers must treat this
    as "fall back to keyword-only retrieval", never as a fatal error."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of corpus documents (task_type=RETRIEVAL_DOCUMENT)."""
        ...

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query (task_type=RETRIEVAL_QUERY — asymmetric from
        document embedding, which is what improves paraphrase recall)."""
        ...
