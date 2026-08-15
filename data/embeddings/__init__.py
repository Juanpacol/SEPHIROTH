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
    live Gemini fallback if an API key is configured. Returns None only if
    `enable_rag_embeddings` is off — callers should treat that the same as
    `EmbeddingUnavailable` (fall back to keyword-only retrieval)."""
    from core.config import settings  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    if not getattr(settings, "enable_rag_embeddings", True):
        return None

    inner = (
        GeminiEmbeddingProvider(api_key=settings.gemini_api_key, model=settings.gemini_embedding_model)
        if settings.gemini_api_key
        else None
    )
    return CachedEmbeddingProvider(inner=inner)
