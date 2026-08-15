"""Manual script: recompute the committed embeddings artifact against the
live Gemini API. Analogous to `intelligence.evaluation.run --mode full
--record` — run by hand (or via a skill) whenever `SEED_GUIDELINES` or the
golden dataset's queries change, never in CI.

    PYTHONPATH=.:platform .venv/bin/python -m data.embeddings.build_artifact
"""

from __future__ import annotations

import gzip
import json
import sys

from data.embeddings.cached import _cache_key
from data.embeddings.corpus_hash import _golden_queries, compute_corpus_sha256
from data.embeddings.gemini import GeminiEmbeddingProvider
from data.rag import SEED_GUIDELINES

ARTIFACT_PATH = "data/embeddings/artifacts/seed_embeddings.json.gz"


def build(api_key: str, model: str = "gemini-embedding-001", dimension: int = 768) -> dict:
    provider = GeminiEmbeddingProvider(api_key=api_key, model=model, dimension=dimension)

    doc_texts = [doc.content for doc in SEED_GUIDELINES]
    doc_vectors = provider.embed_documents(doc_texts)

    queries = _golden_queries()
    query_vectors = [provider.embed_query(q) for q in queries]

    vectors = {}
    for doc, vector in zip(SEED_GUIDELINES, doc_vectors):
        vectors[_cache_key(model, "RETRIEVAL_DOCUMENT", doc.content)] = vector
    for query, vector in zip(queries, query_vectors):
        vectors[_cache_key(model, "RETRIEVAL_QUERY", query)] = vector

    return {
        "model_id": model,
        "dimension": dimension,
        "corpus_sha256": compute_corpus_sha256(),
        "vectors": vectors,
    }


def main() -> int:
    import os

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is not set — cannot build the embeddings artifact.", file=sys.stderr)
        return 1

    artifact = build(api_key)
    with gzip.open(ARTIFACT_PATH, "wt") as f:
        json.dump(artifact, f)
    print(f"Wrote {len(artifact['vectors'])} vectors to {ARTIFACT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
