"""One-time (or re-run-on-demand) population of `guideline_documents` from
the curated Python corpus (`SEED_GUIDELINES`) — SPEC-030/ADR-017 (Phase 15).

Run it after `alembic upgrade head` against any environment that needs real
retrieval (local docker-compose Postgres, Supabase):

    PYTHONPATH=.:platform .venv/bin/python -m data.rag.seed_pgvector

Idempotent: each document is upserted by `id`, so re-running after editing
`SEED_GUIDELINES`/`corpus_primary_care.py` updates existing rows rather than
duplicating them. This is the *only* place `SEED_GUIDELINES` is read at
runtime — everywhere else reads `guideline_documents` (`RAGPipeline`).
"""

from __future__ import annotations

import asyncio
import logging

from data.embeddings.base import EmbeddingProvider, EmbeddingUnavailable
from data.rag import SEED_GUIDELINES

logger = logging.getLogger(__name__)


async def seed_from_python_corpus(embedding_provider: EmbeddingProvider) -> int:
    """Upserts every `Document` in `SEED_GUIDELINES` into
    `guideline_documents`. Returns the number of rows written."""
    from core.db import SessionLocal  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime
    from data.schemas import GuidelineDocument

    written = 0
    async with SessionLocal() as session:
        for doc in SEED_GUIDELINES:
            try:
                vector = embedding_provider.embed_documents([doc.content])[0]
                model_id = embedding_provider.model_id
            except EmbeddingUnavailable:
                logger.warning(
                    "seed_from_python_corpus: no embedding available for %r — seeded keyword-only.",
                    doc.id,
                )
                vector = None
                model_id = None
            await session.merge(
                GuidelineDocument(
                    id=doc.id,
                    content=doc.content,
                    source=doc.source,
                    doc_metadata=doc.metadata,
                    embedding=vector,
                    embedding_model=model_id,
                )
            )
            written += 1
        await session.commit()
    return written


async def _main() -> None:
    from data.embeddings import get_embedding_provider  # noqa: PLC0415

    provider = get_embedding_provider()
    written = await seed_from_python_corpus(provider)
    print(f"Seeded {written} document(s) into guideline_documents.")


if __name__ == "__main__":
    asyncio.run(_main())
