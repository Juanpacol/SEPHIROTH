"""Manual script: recompute the committed embeddings artifact. Analogous to
`intelligence.evaluation.run --mode full --record` — run by hand (or via a
skill) whenever `SEED_GUIDELINES` or the golden dataset's queries change,
never in CI.

    PYTHONPATH=.:platform .venv/bin/python -m data.embeddings.build_artifact
    PYTHONPATH=.:platform .venv/bin/python -m data.embeddings.build_artifact --provider ollama

`--provider ollama` uses the local `OllamaEmbeddingProvider` instead of the
live Gemini API — free, no rate limit, but produces vectors from a
different model. The artifact is single-model: every vector in it (all
documents and golden queries) must come from the same run/provider, never
mixed with a previously committed Gemini-generated artifact.
"""

from __future__ import annotations

import gzip
import json
import sys
import time

from data.embeddings.cached import _cache_key
from data.embeddings.corpus_hash import _golden_queries, compute_corpus_sha256
from data.rag import SEED_GUIDELINES

ARTIFACT_PATH = "data/embeddings/artifacts/seed_embeddings.json.gz"

# The free tier's embed_content quota is per-minute (100 requests observed);
# each `embed_query` call is one request, and the golden dataset's ~90
# queries fired back-to-back exceed it well before the built-in per-call
# retry (max 3 attempts, capped 10s backoff) can recover. A flat pace below
# the limit is simpler and more reliable than deeper retry logic here — this
# script only ever runs by hand, latency doesn't matter. Not needed for the
# local Ollama provider (no quota), but harmless to keep for both.
_QUERY_PACE_SECONDS = 0.8


def build(provider) -> dict:
    doc_texts = [doc.content for doc in SEED_GUIDELINES]
    doc_vectors = provider.embed_documents(doc_texts)

    queries = _golden_queries()
    query_vectors = []
    for q in queries:
        query_vectors.append(provider.embed_query(q))
        time.sleep(_QUERY_PACE_SECONDS)

    vectors = {}
    for doc, vector in zip(SEED_GUIDELINES, doc_vectors):
        vectors[_cache_key(provider.model_id, "RETRIEVAL_DOCUMENT", doc.content)] = vector
    for query, vector in zip(queries, query_vectors):
        vectors[_cache_key(provider.model_id, "RETRIEVAL_QUERY", query)] = vector

    return {
        "model_id": provider.model_id,
        "dimension": provider.dimension,
        "corpus_sha256": compute_corpus_sha256(),
        "vectors": vectors,
    }


def _build_provider(name: str):
    if name == "ollama":
        from data.embeddings.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider()

    import os

    from data.embeddings.gemini import GeminiEmbeddingProvider

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is not set — cannot build the embeddings artifact.", file=sys.stderr)
        return None
    return GeminiEmbeddingProvider(api_key=api_key)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["gemini", "ollama"], default="gemini")
    args = parser.parse_args()

    provider = _build_provider(args.provider)
    if provider is None:
        return 1

    artifact = build(provider)
    with gzip.open(ARTIFACT_PATH, "wt") as f:
        json.dump(artifact, f)
    print(f"Wrote {len(artifact['vectors'])} vectors to {ARTIFACT_PATH} (model={provider.model_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
