"""Tests for FallbackLLMClient — Gemini-first, Groq-on-failure composition.
Uses simple fake clients (not real GeminiClient/GroqClient) to isolate the
fallback logic itself."""

import pytest

from sephiroth.models import ChatResult, LLMUnavailableError
from sephiroth.models.fallback import FallbackLLMClient


class _FakeClient:
    model = "fake-model"

    def __init__(
        self,
        chat_result=None,
        chat_exc=None,
        json_result=None,
        json_exc=None,
        health_result=True,
        supports_vision=True,
        vision_result="primary vision description",
        vision_exc=None,
        vision_stream_chunks=None,
        vision_stream_exc=None,
        vision_stream_fail_after_first=False,
    ):
        self.chat_result = chat_result
        self.chat_exc = chat_exc
        self.json_result = json_result
        self.json_exc = json_exc
        self.health_result = health_result
        self.supports_vision = supports_vision
        self.vision_result = vision_result
        self.vision_exc = vision_exc
        self.vision_stream_chunks = vision_stream_chunks or []
        self.vision_stream_exc = vision_stream_exc
        self.vision_stream_fail_after_first = vision_stream_fail_after_first
        self.chat_calls = 0
        self.json_calls = 0
        self.health_calls = 0
        self.vision_calls = 0
        self.vision_stream_calls = 0

    async def chat(self, **kwargs):
        self.chat_calls += 1
        if self.chat_exc:
            raise self.chat_exc
        return self.chat_result

    async def generate_json(self, *args, **kwargs):
        self.json_calls += 1
        if self.json_exc:
            raise self.json_exc
        return self.json_result

    async def describe_image(self, **kwargs):
        self.vision_calls += 1
        if self.vision_exc:
            raise self.vision_exc
        return self.vision_result

    async def describe_image_stream(self, **kwargs):
        self.vision_stream_calls += 1
        if self.vision_stream_exc and not self.vision_stream_fail_after_first:
            raise self.vision_stream_exc
        for chunk in self.vision_stream_chunks:
            yield chunk
        if self.vision_stream_exc and self.vision_stream_fail_after_first:
            raise self.vision_stream_exc

    async def health(self):
        self.health_calls += 1
        return self.health_result


@pytest.mark.asyncio
async def test_chat_uses_primary_when_it_succeeds():
    primary = _FakeClient(chat_result=ChatResult(content="from primary"))
    secondary = _FakeClient(chat_result=ChatResult(content="from secondary"))
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "from primary"
    assert secondary.chat_calls == 0


@pytest.mark.asyncio
async def test_chat_falls_back_to_secondary_on_primary_failure():
    # AC-001-04 (docs/specs/SPEC-001-model-provider.md)
    primary = _FakeClient(chat_exc=LLMUnavailableError("quota exhausted"))
    secondary = _FakeClient(chat_result=ChatResult(content="from secondary"))
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "from secondary"
    assert primary.chat_calls == 1
    assert secondary.chat_calls == 1


@pytest.mark.asyncio
async def test_chat_propagates_secondary_failure_if_both_fail():
    primary = _FakeClient(chat_exc=LLMUnavailableError("primary down"))
    secondary = _FakeClient(chat_exc=LLMUnavailableError("secondary down too"))
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_generate_json_falls_back_on_primary_failure():
    primary = _FakeClient(json_exc=LLMUnavailableError("quota exhausted"))
    secondary = _FakeClient(json_result={"events": []})
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    result = await client.generate_json("prompt", schema={})
    assert result == {"events": []}


@pytest.mark.asyncio
async def test_describe_image_never_falls_back():
    primary = _FakeClient()
    secondary = _FakeClient()
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    result = await client.describe_image(image_bytes=b"", mime_type="image/png", prompt="describe")
    assert result == "primary vision description"


@pytest.mark.asyncio
async def test_describe_image_does_not_fall_back_if_secondary_has_no_vision():
    """Default posture (secondary.supports_vision=False, e.g. a bare
    GroqClient with no vision_model configured): a primary vision failure
    must propagate, not silently swallow into a fallback that doesn't
    exist. Matches the pre-opt-in behavior exactly."""
    primary = _FakeClient(vision_exc=LLMUnavailableError("gemini vision quota exhausted"))
    secondary = _FakeClient(supports_vision=False)
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    with pytest.raises(LLMUnavailableError):
        await client.describe_image(image_bytes=b"", mime_type="image/png", prompt="describe")
    assert secondary.vision_calls == 0


@pytest.mark.asyncio
async def test_describe_image_falls_back_when_secondary_opted_into_vision():
    primary = _FakeClient(vision_exc=LLMUnavailableError("gemini vision quota exhausted"))
    secondary = _FakeClient(supports_vision=True, vision_result="groq vision description")
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    result = await client.describe_image(image_bytes=b"", mime_type="image/png", prompt="describe")
    assert result == "groq vision description"
    assert secondary.vision_calls == 1


@pytest.mark.asyncio
async def test_describe_image_stream_does_not_fall_back_if_secondary_has_no_vision():
    primary = _FakeClient(vision_stream_exc=LLMUnavailableError("gemini vision quota exhausted"))
    secondary = _FakeClient(supports_vision=False)
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    with pytest.raises(LLMUnavailableError):
        async for _ in client.describe_image_stream(image_bytes=b"", mime_type="image/png", prompt="describe"):
            pass
    assert secondary.vision_stream_calls == 0


@pytest.mark.asyncio
async def test_describe_image_stream_falls_back_when_secondary_opted_into_vision():
    primary = _FakeClient(vision_stream_exc=LLMUnavailableError("gemini vision quota exhausted"))
    secondary = _FakeClient(supports_vision=True, vision_stream_chunks=["groq ", "stream"])
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    chunks = [c async for c in client.describe_image_stream(image_bytes=b"", mime_type="image/png", prompt="describe")]
    assert "".join(chunks) == "groq stream"
    assert secondary.vision_stream_calls == 1


@pytest.mark.asyncio
async def test_describe_image_stream_does_not_retry_once_primary_has_yielded():
    """Once the primary has already streamed a chunk to the caller, a later
    failure must propagate rather than silently restart on the secondary —
    replaying would duplicate content the caller already received."""
    primary = _FakeClient(
        vision_stream_chunks=["partial "],
        vision_stream_exc=LLMUnavailableError("dropped mid-stream"),
        vision_stream_fail_after_first=True,
    )
    secondary = _FakeClient(supports_vision=True, vision_stream_chunks=["should not run"])
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    chunks = []
    with pytest.raises(LLMUnavailableError):
        async for chunk in client.describe_image_stream(image_bytes=b"", mime_type="image/png", prompt="describe"):
            chunks.append(chunk)
    assert chunks == ["partial "]
    assert secondary.vision_stream_calls == 0


@pytest.mark.asyncio
async def test_health_true_if_primary_healthy():
    primary = _FakeClient(health_result=True)
    secondary = _FakeClient(health_result=False)
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    assert await client.health() is True
    assert secondary.health_calls == 0


@pytest.mark.asyncio
async def test_health_true_if_only_secondary_healthy():
    primary = _FakeClient(health_result=False)
    secondary = _FakeClient(health_result=True)
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    assert await client.health() is True


@pytest.mark.asyncio
async def test_health_false_if_both_unhealthy():
    primary = _FakeClient(health_result=False)
    secondary = _FakeClient(health_result=False)
    client = FallbackLLMClient(primary=primary, secondary=secondary)

    assert await client.health() is False


def test_model_attribute_proxies_primary():
    primary = _FakeClient()
    primary.model = "gemini-flash-latest"
    secondary = _FakeClient()
    client = FallbackLLMClient(primary=primary, secondary=secondary)
    assert client.model == "gemini-flash-latest"
