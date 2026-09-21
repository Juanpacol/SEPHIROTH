"""SPEC-030 AC-030-03: the one-time seed script that populates
`guideline_documents` from the Python corpus (`SEED_GUIDELINES`) must be
idempotent — re-running it updates existing rows by id rather than
duplicating them.

Skips automatically when no local Postgres is reachable (AC-030-04), same
pattern as `tests/test_alembic_migration.py`, and when the seed module
itself doesn't exist yet (pre-SF062).
"""

import socket

import pytest

pytest.importorskip("data.rag.seed_pgvector", reason="SPEC-030 not yet implemented — lands in SF062")

LOCAL_POSTGRES_HOST = "localhost"
LOCAL_POSTGRES_PORT = 5433


def _local_postgres_reachable() -> bool:
    try:
        with socket.create_connection((LOCAL_POSTGRES_HOST, LOCAL_POSTGRES_PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _local_postgres_reachable(),
    reason=(
        f"no Postgres reachable at {LOCAL_POSTGRES_HOST}:{LOCAL_POSTGRES_PORT} — "
        "run `docker compose up -d postgres`"
    ),
)


async def test_seeding_twice_leaves_the_table_unchanged():
    from data.embeddings.cached import CachedEmbeddingProvider
    from data.rag import SEED_GUIDELINES
    from data.rag.seed_pgvector import seed_from_python_corpus

    provider = CachedEmbeddingProvider(inner=None)
    first_count = await seed_from_python_corpus(provider)
    second_count = await seed_from_python_corpus(provider)

    assert first_count == len(SEED_GUIDELINES)
    assert second_count == len(SEED_GUIDELINES)
