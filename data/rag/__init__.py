"""
RAG (Retrieval-Augmented Generation) pipeline for medical evidence.

Hybrid retrieval over documents stored in Postgres
(`data.schemas.GuidelineDocument`, pgvector — SPEC-030/ADR-017, Phase 15):
keyword overlap (always available) fused via Reciprocal Rank Fusion with
dense embedding similarity. Every result always carries a citation, and
the output shape is identical regardless of which scoring path fired —
see `RAGPipeline.retrieve()`.
"""

from __future__ import annotations

import logging
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from data.embeddings.base import EmbeddingProvider, EmbeddingUnavailable
from data.rag.document import Document
from data.rag.seed_guidelines import SEED_GUIDELINES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ScoredDoc:
    """A document id + its cosine similarity to a query, from a pgvector
    nearest-neighbor search. Replaces `data.vectors.ScoredDoc`
    (`data/vectors/` was deleted in Phase 15 — SPEC-030/ADR-017 — along
    with the in-memory backend it existed for)."""

    id: str
    score: float


logger = logging.getLogger(__name__)

RRF_K = 60
# Dense embeddings are the more semantically precise signal when available;
# keyword overlap (unweighted by IDF) is a crude fallback prone to noise
# from generic shared words. Weighting dense 2x prevents keyword noise, or
# a near-exact RRF tie, from overriding a clear embedding-model win — see
# `_fuse()`.
KEYWORD_WEIGHT = 1.0
DENSE_WEIGHT = 2.0
# `_fuse` used to truncate straight to `top_k`, leaving `mmr_rerank` in
# `_finalize` nothing to actually diversify against — with an already-top_k
# list, MMR can only reorder, never pull in a relevant doc RRF ranked 6th.
# Widening the fused candidate pool before that final cut lets MMR trade off
# relevance vs. redundancy over real alternatives. See
# tests/test_embeddings_matching.py::test_compound_query_surfaces_all_relevant_documents,
# a 3-topic query where the 2nd and 3rd relevant docs were ranked outside a
# bare top-5 RRF cut.
MMR_CANDIDATE_POOL_MULTIPLIER = 3

STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "for",
    "in",
    "on",
    "to",
    "and",
    "or",
    "what",
    "which",
    "with",
    "how",
    "when",
    "should",
    "be",
    "my",
}


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def _doc_from_row(row: Any) -> Document:
    return Document(id=row.id, content=row.content, source=row.source, metadata=row.doc_metadata or {})


def _retrieve_keyword(query_tokens: set, docs: List[Document]) -> List[Dict[str, Any]]:
    """Today's original scoring: weighted keyword overlap. Pure function of
    an explicit document list — unit-testable with no database.

    Requires at least 2 distinct query tokens to match (when the query has
    that many) — a single shared generic word (e.g. "small" between
    "small-business tax returns" and "a small cut") produced a nonzero
    score against an unrelated document once the corpus grew past ~40
    documents, letting keyword noise alone surface an irrelevant result
    through `_fuse` even when dense retrieval correctly found nothing.
    """
    min_distinct_matches = min(2, len(query_tokens))
    scored = []
    for doc in docs:
        doc_tokens = _tokenize(doc.content)
        if not doc_tokens:
            continue
        matched = query_tokens.intersection(doc_tokens)
        if len(matched) < min_distinct_matches:
            continue
        overlap = sum(1 for t in doc_tokens if t in query_tokens)
        score = overlap / len(doc_tokens) ** 0.5
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "id": doc.id,
            "content": doc.content,
            "source": doc.source,
            "citation": doc.citation,
            "url": doc.metadata.get("url"),
            "score": round(score, 4),
            # No embedding was computed at all on this fallback path (see
            # `retrieve`'s `EmbeddingUnavailable` branch) — never corroborated,
            # same as a keyword-only hit through `_fuse`.
            "dense_similarity": None,
            "metadata": doc.metadata,
        }
        for score, doc in scored
    ]


def _fuse(
    keyword_hits: List[Dict[str, Any]],
    dense_hits: List[ScoredDoc],
    candidate_pool_size: int,
    by_id: Dict[str, Document],
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion, weighted toward the dense signal. Pure
    function of the two hit lists and an explicit id->Document map —
    unit-testable with no database.

    Keyword scoring here isn't IDF-weighted (`score = overlap /
    sqrt(len(doc))`), so short documents sharing only generic words
    with the query (e.g. "patient", "class") can rank artificially
    high — real corpus behavior confirmed empirically while building
    the matching-quality test suite (see tests/test_embeddings_
    matching.py::test_compound_query_surfaces_all_relevant_documents
    and ::test_bp_target_specific_query_does_not_default_to_ckd_
    document). An equal-weight RRF let that keyword noise, or a
    near-exact RRF tie, outrank a real embedding-model win. Dense gets
    2x weight so it can only be overridden by a *clear* keyword
    signal, not by noise or a coin-flip tie.

    Returns `candidate_pool_size` results, not the caller's final
    `top_k` — see `MMR_CANDIDATE_POOL_MULTIPLIER`; the caller's
    `_finalize`/`mmr_rerank` does the actual top_k cut.
    """
    rrf_scores: Dict[str, float] = {}
    for rank, hit in enumerate(keyword_hits):
        rrf_scores[hit["id"]] = rrf_scores.get(hit["id"], 0.0) + KEYWORD_WEIGHT / (RRF_K + rank + 1)
    for rank, scored_doc in enumerate(dense_hits):
        rrf_scores[scored_doc.id] = rrf_scores.get(scored_doc.id, 0.0) + DENSE_WEIGHT / (RRF_K + rank + 1)

    # RRF rank-fuses keyword and dense signals but, by construction, throws
    # away how STRONG a dense match actually was — a 0.64 cosine hit (barely
    # over `min_similarity`) and a 0.95 cosine hit get the same contribution
    # if both are rank-0. That's fine for ranking a handful of results the
    # full pipeline will cite and verify, but `fast_path.py` skips citation
    # guard and claim verification, so it needs the real similarity, not
    # just "some embedding corroborated this." Carried through separately —
    # `None` for a doc that only matched on keyword overlap.
    dense_similarity = {scored_doc.id: scored_doc.score for scored_doc in dense_hits}

    ordered_ids = sorted(rrf_scores.keys(), key=lambda doc_id: rrf_scores[doc_id], reverse=True)
    results = []
    for doc_id in ordered_ids[:candidate_pool_size]:
        doc = by_id.get(doc_id)
        if doc is None:
            continue
        results.append(
            {
                "id": doc.id,
                "content": doc.content,
                "source": doc.source,
                "citation": doc.citation,
                "url": doc.metadata.get("url"),
                "score": round(rrf_scores[doc_id], 4),
                "dense_similarity": dense_similarity.get(doc_id),
                "metadata": doc.metadata,
            }
        )
    return results


class RAGPipeline:
    """Retrieval pipeline over medical documents. Every hit carries a
    citation.

    SPEC-030/ADR-017 (Phase 15): documents and their embeddings live in
    Postgres (`data.schemas.GuidelineDocument`, pgvector), queried fresh on
    every `retrieve()` call — not an in-memory corpus. There is no
    zero-configuration/no-DB mode: `embedding_provider` is required, and a
    call against an unreachable database propagates the underlying
    connection error rather than degrading to keyword-only (`ADR-017`'s
    explicit "no fallback" decision).
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        # Mirrors `settings.retrieval_min_similarity` (platform/core/config.py),
        # which carries the calibration rationale. Duplicated rather than
        # imported because this module must not depend on `platform/` at
        # import time — but the two have to move together, and
        # `tests/test_embeddings_matching.py` fails if they drift.
        min_similarity: float = 0.636,
        session_factory: Optional[Callable[[], "AbstractAsyncContextManager[AsyncSession]"]] = None,
    ):
        self._embedding_provider = embedding_provider
        self._min_similarity = min_similarity
        self._session_factory = session_factory

    def _session(self) -> "AbstractAsyncContextManager[AsyncSession]":
        if self._session_factory is not None:
            return self._session_factory()
        from core.db import SessionLocal  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

        return SessionLocal()

    async def _load_documents(self, session: "AsyncSession") -> List[Document]:
        from sqlalchemy import select

        from data.schemas import GuidelineDocument

        rows = (await session.execute(select(GuidelineDocument))).scalars().all()
        return [_doc_from_row(row) for row in rows]

    async def add_document(self, doc: Document) -> None:
        """Upsert one document (and its embedding, if the configured
        provider can produce one) into `guideline_documents`."""
        from data.schemas import GuidelineDocument

        vector: Optional[List[float]] = None
        try:
            vector = self._embedding_provider.embed_documents([doc.content])[0]
        except EmbeddingUnavailable:
            logger.warning(
                "RAGPipeline.add_document: no embedding available for %r — "
                "stored keyword-only until the artifact/provider catches up.",
                doc.id,
            )
        async with self._session() as session:
            await session.merge(
                GuidelineDocument(
                    id=doc.id,
                    content=doc.content,
                    source=doc.source,
                    doc_metadata=doc.metadata,
                    embedding=vector,
                    embedding_model=self._embedding_provider.model_id if vector is not None else None,
                )
            )
            await session.commit()

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Return the top_k documents as dicts with content, source,
        citation, and score. Hybrid when the query embeds successfully;
        keyword-only otherwise (an `EmbeddingUnavailable` on the *query*
        side, e.g. no cached vector for novel free text, still degrades
        gracefully — only an unreachable *database* propagates, per
        `ADR-017`). Reranked for diversity and content-budgeted
        (`src/sephiroth/context/`) before returning."""
        from sqlalchemy import select

        from data.schemas import GuidelineDocument

        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        async with self._session() as session:
            docs = await self._load_documents(session)
            keyword_hits = _retrieve_keyword(query_tokens, docs)

            try:
                query_vector = self._embedding_provider.embed_query(query)
            except EmbeddingUnavailable:
                return self._finalize(keyword_hits, top_k)

            candidate_pool_size = top_k * MMR_CANDIDATE_POOL_MULTIPLIER
            distance = GuidelineDocument.embedding.cosine_distance(query_vector)
            rows = (
                await session.execute(
                    select(GuidelineDocument.id, distance.label("distance"))
                    .where(GuidelineDocument.embedding.isnot(None))
                    .order_by(distance)
                    .limit(candidate_pool_size)
                )
            ).all()
            dense_hits = [
                ScoredDoc(id=row.id, score=1.0 - row.distance)
                for row in rows
                if (1.0 - row.distance) >= self._min_similarity
            ]

        by_id = {doc.id: doc for doc in docs}
        fused = _fuse(keyword_hits, dense_hits, candidate_pool_size, by_id)
        return self._finalize(fused, top_k)

    def _finalize(self, hits: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        from core.config import settings
        from sephiroth.context import mmr_rerank, truncate

        reranked = mmr_rerank(hits, top_k=top_k)
        for hit in reranked:
            if hit.get("content"):
                hit["content"] = truncate(hit["content"], settings.max_context_chars)
        return reranked


__all__ = ["RAGPipeline", "Document", "SEED_GUIDELINES"]
