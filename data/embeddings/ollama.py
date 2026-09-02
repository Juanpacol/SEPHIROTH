"""Local embedding provider backed by Ollama's OpenAI-compatible
`/v1/embeddings` endpoint. Free, unlimited iteration, no API key — the
embedding-side counterpart to `sephiroth.models.ollama.OllamaClient`, used
when the Gemini free-tier quota for `embed_content` is unavailable.

Not wired into `get_embedding_provider()` by default: Gemini stays the
runtime default (see that function's docstring). Vectors from a different
embedding model are not comparable to Gemini's — regenerating the
committed artifact with this provider means every vector in it (all
documents and golden queries) must come from the same model, never a mix.
"""

from __future__ import annotations

from typing import List

import httpx

from .base import EmbeddingUnavailable

DEFAULT_BASE_URL = "http://localhost:11434/v1"
_TIMEOUT_SECONDS = 60


class OllamaEmbeddingProvider:
    """Synchronous wrapper around Ollama's `/v1/embeddings` endpoint."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = DEFAULT_BASE_URL,
        dimension: int = 768,
        timeout_seconds: int = _TIMEOUT_SECONDS,
    ):
        self.model_id = model
        self.dimension = dimension
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def _embed(self, texts: List[str]) -> List[List[float]]:
        try:
            response = httpx.post(
                f"{self._base_url}/embeddings",
                json={"model": self.model_id, "input": texts},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailable(str(exc)) from exc

        payload = response.json()
        return [item["embedding"] for item in payload["data"]]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]


__all__ = ["OllamaEmbeddingProvider"]
