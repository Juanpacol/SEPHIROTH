"""Tests for VisionChatSplitClient — chat/generate_json go to `chat_client`,
describe_image(_stream)/vision support go to `vision_client`, using
FakeLLMClient doubles so no real provider is touched."""

import pytest

from sephiroth.models.base import ChatResult
from sephiroth.models.vision_split import VisionChatSplitClient
from tests.conftest import FakeLLMClient


class _RecordingClient(FakeLLMClient):
    def __init__(self, *, supports_vision=False, **kwargs):
        super().__init__(**kwargs)
        self._supports_vision = supports_vision
        self.chat_called = False
        self.describe_called = False

    @property
    def supports_vision(self):
        return self._supports_vision

    async def chat(self, *args, **kwargs):
        self.chat_called = True
        return ChatResult(content="chat response")

    async def describe_image(self, **kwargs):
        self.describe_called = True
        return "vision response"

    async def describe_image_stream(self, **kwargs):
        self.describe_called = True
        for chunk in ["a", "b"]:
            yield chunk

    async def health(self):
        return True


@pytest.mark.asyncio
async def test_chat_routes_to_chat_client_not_vision_client():
    chat_client = _RecordingClient()
    vision_client = _RecordingClient(supports_vision=True)
    split = VisionChatSplitClient(chat_client=chat_client, vision_client=vision_client)

    result = await split.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "chat response"
    assert chat_client.chat_called is True
    assert vision_client.chat_called is False


@pytest.mark.asyncio
async def test_describe_image_routes_to_vision_client_not_chat_client():
    chat_client = _RecordingClient()
    vision_client = _RecordingClient(supports_vision=True)
    split = VisionChatSplitClient(chat_client=chat_client, vision_client=vision_client)

    result = await split.describe_image(image_bytes=b"x", mime_type="image/png", prompt="describe")

    assert result == "vision response"
    assert vision_client.describe_called is True
    assert chat_client.describe_called is False


@pytest.mark.asyncio
async def test_describe_image_stream_routes_to_vision_client():
    chat_client = _RecordingClient()
    vision_client = _RecordingClient(supports_vision=True)
    split = VisionChatSplitClient(chat_client=chat_client, vision_client=vision_client)

    chunks = [
        c async for c in split.describe_image_stream(image_bytes=b"x", mime_type="image/png", prompt="d")
    ]

    assert chunks == ["a", "b"]
    assert vision_client.describe_called is True


def test_supports_vision_proxies_vision_client_not_chat_client():
    chat_client = _RecordingClient(supports_vision=False)
    vision_client = _RecordingClient(supports_vision=True)
    split = VisionChatSplitClient(chat_client=chat_client, vision_client=vision_client)
    assert split.supports_vision is True


@pytest.mark.asyncio
async def test_health_requires_both_clients_healthy():
    class _UnhealthyClient(_RecordingClient):
        async def health(self):
            return False

    chat_client = _RecordingClient()
    vision_client = _UnhealthyClient(supports_vision=True)
    split = VisionChatSplitClient(chat_client=chat_client, vision_client=vision_client)
    assert await split.health() is False
