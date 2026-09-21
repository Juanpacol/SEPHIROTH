"""guideline documents embedding index

SPEC-030/ADR-017 (Phase 15): `guideline_documents.embedding` goes from a
never-queried column to the RAG corpus's live storage, queried on every
`RAGPipeline.retrieve()` call — this is the index that was intentionally
deferred (`data/schemas/__init__.py::GuidelineDocument`'s prior docstring)
until real rows existed to index against.

IVFFlat (not HNSW): universally supported since pgvector 0.1.0, so it
works identically on the local docker-compose Postgres and on whatever
pgvector extension version Supabase happens to have enabled, without
needing to verify HNSW support on both first. `lists=10` — pgvector's own
guidance (`rows / 1000`, floored at a small constant) for a corpus in the
tens-to-low-hundreds; revisit if the corpus grows by an order of
magnitude (SPEC-030 NG-3).

`CONCURRENTLY` is not used: this table has no live writers today (a
migration always runs inside its own transaction anyway, and
`CONCURRENTLY` cannot run inside one) — see SPEC-030 NG-1, no ingestion
endpoint exists yet to contend with a lock.

Revision ID: 32224bacb219
Revises: 935983ae77bf
Create Date: 2026-09-20 22:49:05.649004

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "32224bacb219"
down_revision: Union[str, Sequence[str], None] = "935983ae77bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_guideline_documents_embedding_cosine "
        "ON guideline_documents USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 10)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_guideline_documents_embedding_cosine")
