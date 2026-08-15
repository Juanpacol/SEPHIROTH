"""Cache-backed embedding provider over a committed JSON(.gz) artifact.

Used everywhere retrieval must stay deterministic and offline (CI's
`--mode ci`, the whole test suite): a cache hit returns instantly with no
network; a miss with no live `inner` provider raises `EmbeddingUnavailable`
rather than ever reaching out — this is what makes `RAGPipeline()` safe to
construct with zero configuration.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from .base import EmbeddingProvider, EmbeddingUnavailable

DEFAULT_ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "seed_embeddings.json.gz"


def _cache_key(model_id: str, task_type: str, text: str) -> str:
    digest = hashlib.sha256(f"{model_id}\x00{task_type}\x00{text}".encode()).hexdigest()
    return digest


def load_artifact(path: Path = DEFAULT_ARTIFACT_PATH) -> Optional[dict]:
    if not path.exists():
        return None
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        return json.load(f)


class CachedEmbeddingProvider:
    """Wraps an optional live `inner` provider with a persistent cache.

    `inner=None` means "cache-only" — the shape CI and tests always use.
    `inner=<GeminiEmbeddingProvider>` means "cache first, live on miss" —
    the shape used when building/refreshing the artifact (see
    `build_artifact.py`) or serving a live query the artifact didn't
    precompute (e.g. a brand-new user query at runtime).
    """

    def __init__(
        self,
        inner: Optional[EmbeddingProvider],
        artifact_path: Path = DEFAULT_ARTIFACT_PATH,
    ):
        self._inner = inner
        self._artifact_path = artifact_path
        artifact = load_artifact(artifact_path)
        if artifact is None:
            self.model_id = getattr(inner, "model_id", "gemini-embedding-001")
            self.dimension = getattr(inner, "dimension", 768)
            self._cache: Dict[str, List[float]] = {}
            self.corpus_sha256: Optional[str] = None
        else:
            self.model_id = artifact["model_id"]
            self.dimension = artifact["dimension"]
            self._cache = dict(artifact["vectors"])
            self.corpus_sha256 = artifact.get("corpus_sha256")

    def _get_or_compute(self, text: str, task_type: str) -> List[float]:
        key = _cache_key(self.model_id, task_type, text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if self._inner is None:
            raise EmbeddingUnavailable(
                f"No cached embedding for this text (task_type={task_type}) and no live "
                "provider configured — falling back to keyword-only retrieval."
            )
        if task_type == "RETRIEVAL_QUERY":
            vector = self._inner.embed_query(text)
        else:
            vector = self._inner.embed_documents([text])[0]
        self._cache[key] = vector  # extend the in-process cache for this run only
        return vector

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._get_or_compute(t, "RETRIEVAL_DOCUMENT") for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._get_or_compute(text, "RETRIEVAL_QUERY")
