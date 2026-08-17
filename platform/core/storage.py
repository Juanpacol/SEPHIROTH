"""Attachment byte storage — a narrow seam behind `ResultAttachment.content`.

Bytes live in Postgres today (see `data.schemas.ResultAttachment`'s
docstring for why: no persistent filesystem on Render's free tier, no new
infra for an MVP shipping zero files). This `Protocol` exists so a later
move to S3/object storage is one new class, not a router rewrite —
routers call `get_blob_store()`, never `ResultAttachment.content`
directly outside this module.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from data.schemas import ResultAttachment


class BlobStore(Protocol):
    async def get(self, session: AsyncSession, attachment_id: str) -> bytes | None: ...


class DatabaseBlobStore:
    """Reads attachment bytes from the same row `content` is stored on.
    `content` is `deferred=True` on the model, so a plain `session.get`
    would still fetch it lazily (fine for a single-row read) — `undefer`
    makes the one round trip explicit rather than relying on the lazy
    default."""

    async def get(self, session: AsyncSession, attachment_id: str) -> bytes | None:
        row = await session.scalar(
            select(ResultAttachment)
            .where(ResultAttachment.id == attachment_id)
            .options(undefer(ResultAttachment.content))
        )
        return row.content if row is not None else None


_store = DatabaseBlobStore()


def get_blob_store() -> BlobStore:
    return _store
