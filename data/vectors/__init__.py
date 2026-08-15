"""Vector storage and operations. `InMemoryVectorStore` is the default,
used for all hot-path retrieval scoring. pgvector (see `data/schemas`) is
used only to persist documents ingested via the API — not for retrieval."""

from .base import ScoredDoc, VectorStore
from .memory import InMemoryVectorStore

__all__ = ["ScoredDoc", "VectorStore", "InMemoryVectorStore"]
