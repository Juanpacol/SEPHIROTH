"""Embedding models and utilities — Gemini embeddings at runtime, a
committed artifact for offline/CI use. See `base.py` for the provider
protocol and `cached.py` for the artifact-backed provider."""

from __future__ import annotations

from typing import Optional

from .base import EmbeddingProvider, EmbeddingUnavailable
from .cached import DEFAULT_ARTIFACT_PATH, CachedEmbeddingProvider
from .gemini import GeminiEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingUnavailable",
    "CachedEmbeddingProvider",
    "DEFAULT_ARTIFACT_PATH",
    "GeminiEmbeddingProvider",
    "get_embedding_provider",
]


def get_embedding_provider() -> Optional[CachedEmbeddingProvider]:
    """Build the default embedding provider from settings: cache-first,
    live fallback on a cache miss. Returns None only if
    `enable_rag_embeddings` is off — callers should treat that the same as
    `EmbeddingUnavailable` (fall back to keyword-only retrieval).

    The live (cache-miss) provider must always match whichever model
    produced the committed artifact — vectors from two different embedding
    models are not comparable, mixing them silently corrupts similarity
    scores. `llm_provider="ollama"` (local dev, no Gemini quota) routes
    here too, via `OllamaEmbeddingProvider`, so a fresh query at runtime
    stays in the same vector space as an Ollama-built artifact."""
    from core.config import settings  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    if not getattr(settings, "enable_rag_embeddings", True):
        return None

    if settings.llm_provider == "ollama":
        from .ollama import OllamaEmbeddingProvider  # noqa: PLC0415 — avoid a hard httpx dep at import time

        inner = OllamaEmbeddingProvider(base_url=settings.ollama_base_url)
    elif settings.gemini_api_key:
        inner = GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key, model=settings.gemini_embedding_model
        )
    else:
        inner = None
    return CachedEmbeddingProvider(inner=inner)
