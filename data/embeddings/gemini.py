"""Live embedding provider backed by the Gemini embeddings API
(`gemini-embedding-001`). Used at runtime when `GEMINI_API_KEY` is set;
CI and tests use `CachedEmbeddingProvider` over a committed artifact instead
(see cached.py) so nothing here ever runs in the offline eval gate."""

from __future__ import annotations

import math
import time
from typing import Callable, List, Optional

from google import genai
from google.genai import errors, types

from .base import EmbeddingUnavailable

_MAX_RETRIES = 3


def _normalize(vector: List[float]) -> List[float]:
    """Re-normalize to unit L2 norm. Required after Matryoshka (MRL)
    truncation to a smaller `output_dimensionality` — the truncated vector
    is no longer unit-norm, and cosine-via-dot-product silently gives wrong
    (deflated) similarities without this."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


class GeminiEmbeddingProvider:
    """Synchronous wrapper around `genai.Client(...).models.embed_content`."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "gemini-embedding-001",
        dimension: int = 768,
        max_retries: int = _MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model_id = model
        self.dimension = dimension
        self.max_retries = max_retries
        self._sleep = sleep
        self._client: Optional[genai.Client] = genai.Client(api_key=api_key) if api_key else None

    def _embed(self, texts: List[str], task_type: str) -> List[List[float]]:
        if self._client is None:
            raise EmbeddingUnavailable("GEMINI_API_KEY is not configured.")
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dimension)
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.models.embed_content(
                    model=self.model_id, contents=texts, config=config
                )
                return [_normalize(list(e.values)) for e in response.embeddings]
            except errors.ClientError as exc:
                if exc.code == 429 and attempt < self.max_retries - 1:
                    self._sleep(min(2**attempt, 10))
                    last_exc = exc
                    continue
                raise EmbeddingUnavailable(str(exc)) from exc
            except errors.ServerError as exc:
                if attempt < self.max_retries - 1:
                    self._sleep(min(2**attempt, 10))
                    last_exc = exc
                    continue
                raise EmbeddingUnavailable(str(exc)) from exc
        raise EmbeddingUnavailable(str(last_exc) if last_exc else "embedding request failed")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text], task_type="RETRIEVAL_QUERY")[0]
