"""Attachment byte storage — a narrow seam behind `ResultAttachment.content`.

Bytes live in Postgres by default (see `data.schemas.ResultAttachment`'s
docstring for why: no persistent filesystem on Render's free tier). This
`Protocol` exists so routers never touch `ResultAttachment.content`
directly — only `get_blob_store()` — so swapping the backend is a config
value (`settings.storage_backend`), not a router rewrite. `S3BlobStore`
requires real bucket credentials to actually use; until those are
configured, the default stays `PostgresBlobStore` and nothing changes.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from core.config import settings
from data.schemas import ResultAttachment


class BlobStore(Protocol):
    async def get(self, session: AsyncSession, attachment_id: str) -> bytes | None: ...
    async def put(self, session: AsyncSession, attachment_id: str, data: bytes) -> None: ...


class PostgresBlobStore:
    """Reads/writes attachment bytes on the same row as everything else.
    `content` is `deferred=True` on the model, so a plain `session.get`
    would still fetch it lazily (fine for a single-row read) — `undefer`
    makes the one round trip explicit rather than relying on the lazy
    default. `put` only sets the in-memory attribute — the caller is
    still responsible for `session.add`/`session.commit` on the row,
    same as before this seam existed."""

    async def get(self, session: AsyncSession, attachment_id: str) -> bytes | None:
        row = await session.scalar(
            select(ResultAttachment)
            .where(ResultAttachment.id == attachment_id)
            .options(undefer(ResultAttachment.content))
        )
        return row.content if row is not None else None

    async def put(self, session: AsyncSession, attachment_id: str, data: bytes) -> None:
        row = await session.get(ResultAttachment, attachment_id)
        if row is not None:
            row.content = data


class S3BlobStore:
    """Stores attachment bytes in an S3(-compatible) bucket, keyed by
    `attachment_id`; `ResultAttachment.content` stays NULL for these rows
    (see the model's docstring). Credentials come from the standard
    boto3 chain (env vars, shared config, or an IAM role) — never read
    from `Settings` or logged. Requires `settings.s3_bucket` to be set;
    this class is only reachable when `settings.storage_backend == "s3"`."""

    def __init__(self, bucket: str, region: str):
        self._bucket = bucket
        self._region = region
        self._client = None

    def _s3(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    async def get(self, session: AsyncSession, attachment_id: str) -> bytes | None:
        import asyncio

        from botocore.exceptions import ClientError

        def _get() -> bytes | None:
            try:
                obj = self._s3().get_object(Bucket=self._bucket, Key=attachment_id)
                return obj["Body"].read()
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    return None
                raise

        return await asyncio.to_thread(_get)

    async def put(self, session: AsyncSession, attachment_id: str, data: bytes) -> None:
        import asyncio

        await asyncio.to_thread(self._s3().put_object, Bucket=self._bucket, Key=attachment_id, Body=data)


_store: BlobStore | None = None


def get_blob_store() -> BlobStore:
    global _store
    if _store is not None:
        return _store
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("storage_backend='s3' requires settings.s3_bucket to be set")
        _store = S3BlobStore(settings.s3_bucket, settings.s3_region)
    else:
        _store = PostgresBlobStore()
    return _store
