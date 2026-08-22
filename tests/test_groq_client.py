"""Tests for GroqClient, mocking the HTTP transport with `httpx.MockTransport`
— no real network calls. Mirrors the contract tests in test_gemini_client.py
since both clients expose the same chat()/generate_json()/health() shape.

Verifies AC-006-08 (docs/specs/SPEC-006-telemetry.md)."""

import json as json_mod

import httpx
import pytest

from sephiroth.models import LLMUnavailableError
from sephiroth.models.groq import GroqClient


async def _noop_sleep(_seconds):
    return None


def _openai_response(content=None, tool_calls=None, usage=None):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    body = {"choices": [{"message": message}]}
    if usage:
        body["usage"] = {"prompt_tokens": usage[0], "completion_tokens": usage[1]}
    return body


def _make_client(handler, **kwargs):
    client = GroqClient(api_key="fake-key", sleep=_noop_sleep, **kwargs)
    client._client = httpx.AsyncClient(
        base_url="https://api.groq.com/openai/v1",
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_chat_no_tool_calls_returns_content():
    def handler(request):
        return httpx.Response(200, json=_openai_response(content="Hello there"))

    client = _make_client(handler)
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "Hello there"
    assert result.tool_calls == []
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_chat_reports_real_usage_when_present():
    def handler(request):
        return httpx.Response(200, json=_openai_response(content="Hello there", usage=(12, 34)))

    client = _make_client(handler)
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 34


@pytest.mark.asyncio
async def test_chat_usage_defaults_to_zero_when_absent():
    def handler(request):
        return httpx.Response(200, json=_openai_response(content="Hello there"))

    client = _make_client(handler)
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


@pytest.mark.asyncio
async def test_chat_executes_tool_call_and_appends_result():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json=_openai_response(
                    tool_calls=[
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "my_tool", "arguments": json_mod.dumps({"q": "x"})},
                        }
                    ]
                ),
            )
        return httpx.Response(200, json=_openai_response(content="Final answer"))

    client = _make_client(handler)

    async def executor(name, args):
        assert name == "my_tool"
        assert args == {"q": "x"}
        return {"ok": True}

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], tool_executor=executor)
    assert result.content == "Final answer"
    assert result.tool_calls == [{"name": "my_tool", "arguments": {"q": "x"}, "result": {"ok": True}}]
    assert result.rounds == 2


@pytest.mark.asyncio
async def test_chat_tool_exception_surfaces_as_error_result():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json=_openai_response(
                    tool_calls=[
                        {"id": "call_1", "type": "function", "function": {"name": "boom", "arguments": "{}"}}
                    ]
                ),
            )
        return httpx.Response(200, json=_openai_response(content="recovered"))

    client = _make_client(handler)

    async def executor(name, args):
        raise RuntimeError("tool blew up")

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.tool_calls[0]["result"] == {"error": "tool blew up"}
    assert result.content == "recovered"


@pytest.mark.asyncio
async def test_chat_hits_max_tool_rounds_cap():
    def handler(request):
        return httpx.Response(
            200,
            json=_openai_response(
                tool_calls=[
                    {"id": "call_1", "type": "function", "function": {"name": "loop_tool", "arguments": "{}"}}
                ]
            ),
        )

    client = _make_client(handler, max_tool_rounds=3)

    async def executor(name, args):
        return {}

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.rounds == 3
    assert "limit reached" in result.content.lower()


@pytest.mark.asyncio
async def test_chat_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=_openai_response(content="ok"))

    client = _make_client(handler, max_retries=2)
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_chat_persistent_429_raises_unavailable():
    def handler(request):
        return httpx.Response(429, text="rate limited")

    client = _make_client(handler, max_retries=2)
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_400_does_not_retry():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    client = _make_client(handler, max_retries=3)
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_tool_use_failed_retries_round_without_tools():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            assert b"tools" in request.content
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Failed to call a function.",
                        "type": "invalid_request_error",
                        "code": "tool_use_failed",
                        "failed_generation": "<function=search [...]>",
                    }
                },
            )
        assert b'"tools"' not in request.content
        return httpx.Response(200, json=_openai_response(content="answered without tools"))

    client = _make_client(handler)
    result = await client.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "search"}}],
    )
    assert result.content == "answered without tools"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_no_api_key_raises_unavailable():
    client = GroqClient(api_key=None, sleep=_noop_sleep)
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert await client.health() is False


@pytest.mark.asyncio
async def test_generate_json_parses_response():
    def handler(request):
        return httpx.Response(200, json=_openai_response(content='{"supported": true}'))

    client = _make_client(handler)
    result = await client.generate_json("prompt", schema={"type": "object"})
    assert result == {"supported": True}


@pytest.mark.asyncio
async def test_health_true_on_200():
    def handler(request):
        return httpx.Response(200, json={"data": []})

    client = _make_client(handler)
    assert await client.health() is True


@pytest.mark.asyncio
async def test_health_false_on_error():
    def handler(request):
        raise httpx.ConnectError("no network")

    client = _make_client(handler)
    assert await client.health() is False


@pytest.mark.asyncio
async def test_describe_image_not_supported():
    # AC-001-05 (docs/specs/SPEC-001-model-provider.md) — default posture,
    # no vision_model configured.
    client = GroqClient(api_key="fake-key", sleep=_noop_sleep)
    assert client.supports_vision is False
    with pytest.raises(LLMUnavailableError):
        await client.describe_image(image_bytes=b"", mime_type="image/png", prompt="describe")


@pytest.mark.asyncio
async def test_describe_image_uses_configured_vision_model():
    captured = {}

    def handler(request):
        captured["body"] = json_mod.loads(request.content)
        return httpx.Response(200, json=_openai_response(content="Bilateral infiltrates visible."))

    client = _make_client(handler, vision_model="llama-3.2-90b-vision-preview")
    assert client.supports_vision is True

    result = await client.describe_image(
        image_bytes=b"fake-bytes", mime_type="image/png", prompt="describe this"
    )

    assert result == "Bilateral infiltrates visible."
    assert captured["body"]["model"] == "llama-3.2-90b-vision-preview"
    content = captured["body"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "describe this"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_describe_image_stream_yields_chunks_in_order():
    sse_body = (
        b'data: {"choices":[{"delta":{"content":"Bilateral "}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"infiltrates."}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    client = _make_client(handler, vision_model="llama-3.2-90b-vision-preview")

    chunks = [
        c
        async for c in client.describe_image_stream(
            image_bytes=b"fake-bytes", mime_type="image/png", prompt="describe"
        )
    ]
    assert "".join(chunks) == "Bilateral infiltrates."


@pytest.mark.asyncio
async def test_describe_image_stream_not_supported_without_vision_model():
    client = GroqClient(api_key="fake-key", sleep=_noop_sleep)
    with pytest.raises(LLMUnavailableError):
        async for _ in client.describe_image_stream(
            image_bytes=b"", mime_type="image/png", prompt="describe"
        ):
            pass


@pytest.mark.asyncio
async def test_describe_image_stream_error_status_raises_unavailable():
    def handler(request):
        return httpx.Response(429, text="rate limited")

    client = _make_client(handler, vision_model="llama-3.2-90b-vision-preview")
    with pytest.raises(LLMUnavailableError):
        async for _ in client.describe_image_stream(
            image_bytes=b"", mime_type="image/png", prompt="describe"
        ):
            pass
