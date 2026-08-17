"""`S3BlobStore` — the object-storage backend behind `platform/core/
storage.py::BlobStore`. Mocked via `moto`, no real bucket needed. Never
touches `get_blob_store()`'s config-driven singleton directly — these
tests instantiate `S3BlobStore` themselves so they don't depend on
`settings.storage_backend` being flipped globally."""

import boto3
import pytest
from moto import mock_aws

import core.storage as storage_module
from core.storage import PostgresBlobStore, S3BlobStore

BUCKET = "sephiroth-test-attachments"
REGION = "us-east-1"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        yield


@pytest.mark.asyncio
async def test_put_then_get_roundtrips_bytes(s3_bucket):
    store = S3BlobStore(BUCKET, REGION)
    await store.put(None, "attachment-1", b"hello world")
    result = await store.get(None, "attachment-1")
    assert result == b"hello world"


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(s3_bucket):
    store = S3BlobStore(BUCKET, REGION)
    result = await store.get(None, "does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_put_overwrites_existing_key(s3_bucket):
    store = S3BlobStore(BUCKET, REGION)
    await store.put(None, "attachment-2", b"first version")
    await store.put(None, "attachment-2", b"second version")
    result = await store.get(None, "attachment-2")
    assert result == b"second version"


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """`get_blob_store()` caches its instance in a module global — reset
    it around each test so one test's backend choice can't leak into
    another test in this file."""
    monkeypatch.setattr(storage_module, "_store", None)
    yield
    monkeypatch.setattr(storage_module, "_store", None)


def test_get_blob_store_defaults_to_postgres(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "storage_backend", "postgres")
    assert isinstance(storage_module.get_blob_store(), PostgresBlobStore)


def test_get_blob_store_returns_s3_when_configured(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "storage_backend", "s3")
    monkeypatch.setattr(storage_module.settings, "s3_bucket", BUCKET)
    store = storage_module.get_blob_store()
    assert isinstance(store, S3BlobStore)


def test_get_blob_store_s3_without_bucket_raises(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "storage_backend", "s3")
    monkeypatch.setattr(storage_module.settings, "s3_bucket", None)
    with pytest.raises(RuntimeError):
        storage_module.get_blob_store()
