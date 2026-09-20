"""Embedding models and utilities — Gemini embeddings at runtime, a
committed artifact for offline/CI use. See `base.py` for the provider
protocol and `cached.py` for the artifact-backed provider."""

from __future__ import annotations

import logging
from typing import Optional

from .base import EmbeddingProvider, EmbeddingUnavailable
from .cached import DEFAULT_ARTIFACT_PATH, CachedEmbeddingProvider, load_artifact
from .gemini import GeminiEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingUnavailable",
    "CachedEmbeddingProvider",
    "DEFAULT_ARTIFACT_PATH",
    "GeminiEmbeddingProvider",
    "get_embedding_provider",
]

logger = logging.getLogger(__name__)

# Model-id prefixes/exact ids that identify a Gemini-served embedding model.
# Anything else — notably "nomic-embed-text" — is treated as Ollama-served.
# An unrecognized id defaults to the *local* provider because that is the
# fail-safe direction: worst case is keyword-only retrieval, the other
# direction leaks a query to a paid third-party API.
_GEMINI_EMBEDDING_PREFIXES = ("gemini-", "text-embedding-", "models/")


def _is_gemini_embedding_model(model_id: str) -> bool:
    return model_id.startswith(_GEMINI_EMBEDDING_PREFIXES) or model_id == "embedding-001"


def get_embedding_provider() -> Optional[CachedEmbeddingProvider]:
    """Build the default embedding provider from settings: cache-first,
    live fallback on a cache miss. Returns None only if
    `enable_rag_embeddings` is off — callers should treat that the same as
    `EmbeddingUnavailable` (fall back to keyword-only retrieval).

    The live cache-miss provider is chosen by the committed artifact's own
    `model_id`, never by `llm_provider`, because vectors from two embedding
    models are not comparable. The sole exception: a local `llm_provider`
    never constructs a Gemini provider, falling back to cache-only instead
    — so cache misses degrade to keyword-only retrieval rather than mixing
    vector spaces, but the local-only guarantee always wins.

    Production consequence (deliberate — see the local-only isolation
    spec's Decision D4): with the committed `nomic-embed-text` artifact and
    `llm_provider="gemini"`, a cache miss now uses `OllamaEmbeddingProvider`
    (matching the artifact), not `GeminiEmbeddingProvider` — a novel query
    against an unreachable local Ollama degrades to keyword-only retrieval
    instead of silently scoring a `gemini-embedding-001` vector against
    `nomic-embed-text` document vectors. Cache hits (the entire seed
    guideline corpus and every golden query) are unaffected either way.
    """
    from core.config import (  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime
        is_local_llm_provider,
        settings,
    )

    if not getattr(settings, "enable_rag_embeddings", True):
        return None

    # Loaded again just below by `CachedEmbeddingProvider.__init__` — accepted
    # duplication: this runs once per process, the artifact is ~176 vectors,
    # and reaching into `CachedEmbeddingProvider._inner` after construction
    # would break its encapsulation instead.
    artifact = load_artifact(DEFAULT_ARTIFACT_PATH)
    artifact_model_id = artifact["model_id"] if artifact is not None else None
    artifact_dimension = artifact["dimension"] if artifact is not None else None

    inner: Optional[EmbeddingProvider]
    if artifact_model_id is None:
        # No artifact at all — preserve the old provider-keyed behavior.
        if is_local_llm_provider(settings.llm_provider):
            from .ollama import (
                OllamaEmbeddingProvider,  # noqa: PLC0415 — avoid a hard httpx dep at import time
            )

            inner = OllamaEmbeddingProvider(
                base_url=settings.ollama_base_url, dimension=settings.embedding_dimension
            )
        elif settings.gemini_api_key:
            inner = GeminiEmbeddingProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_embedding_model,
                dimension=settings.embedding_dimension,
                timeout_seconds=settings.gemini_timeout_seconds,
            )
        else:
            inner = None
    elif _is_gemini_embedding_model(artifact_model_id):
        if is_local_llm_provider(settings.llm_provider):
            logger.warning(
                "Embedding artifact model_id=%r is a Gemini model, but llm_provider=%r is "
                "local-only; the local-only guarantee wins over artifact matching. Cache "
                "misses will degrade to keyword-only retrieval rather than call Gemini.",
                artifact_model_id,
                settings.llm_provider,
            )
            inner = None
        elif settings.gemini_api_key:
            inner = GeminiEmbeddingProvider(
                api_key=settings.gemini_api_key,
                model=artifact_model_id,
                dimension=artifact_dimension,
                timeout_seconds=settings.gemini_timeout_seconds,
            )
        else:
            inner = None
    else:
        # Non-Gemini (Ollama-served) artifact model — for every value of
        # llm_provider, including "gemini" and "groq".
        from .ollama import OllamaEmbeddingProvider  # noqa: PLC0415 — avoid a hard httpx dep at import time

        if not is_local_llm_provider(settings.llm_provider):
            logger.info(
                "Embedding artifact model_id=%r is Ollama-served; cache misses will call "
                "Ollama at %r even though llm_provider=%r.",
                artifact_model_id,
                settings.ollama_base_url,
                settings.llm_provider,
            )
        inner = OllamaEmbeddingProvider(
            model=artifact_model_id, base_url=settings.ollama_base_url, dimension=artifact_dimension
        )

    # Pass `artifact_path` explicitly (rather than relying on
    # `CachedEmbeddingProvider`'s own default, which is bound at function
    # definition time) so this stays in step with the `DEFAULT_ARTIFACT_PATH`
    # resolved above, including in tests that monkeypatch it.
    return CachedEmbeddingProvider(inner=inner, artifact_path=DEFAULT_ARTIFACT_PATH)
