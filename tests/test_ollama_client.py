"""Tests for OllamaClient, mocking the HTTP transport with `httpx.MockTransport`
— no real Ollama server needed. Mirrors test_groq_client.py since both clients
implement the same OpenAI-compatible chat completions shape (text/tools).
Vision goes through Ollama's native `/api/chat` instead — see
`OllamaClient._native_api_url`'s docstring for why."""

import base64
import json as json_mod

import httpx
import pytest

from sephiroth.models import LLMUnavailableError
from sephiroth.models.ollama import OllamaClient

# Smallest possible valid PNG (1x1 transparent pixel) — real image bytes are
# required since `_downscale_for_vision` decodes them with PIL before any
# HTTP call is made.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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
    client = OllamaClient(sleep=_noop_sleep, **kwargs)
    client._client = httpx.AsyncClient(
        base_url="http://localhost:11434/v1",
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
async def test_chat_model_not_found_raises_helpful_error():
    def handler(request):
        return httpx.Response(404, text="model not found")

    client = _make_client(handler, model="qwen2.5:14b")
    with pytest.raises(LLMUnavailableError, match="ollama pull qwen2.5:14b"):
        await client.chat(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_connect_error_mentions_ollama_serve():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = _make_client(handler, max_retries=1)
    with pytest.raises(LLMUnavailableError, match="ollama serve"):
        await client.chat(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_no_api_key_needed_locally():
    """Unlike Groq, Ollama requires no API key by default — chat should not
    raise LLMUnavailableError purely for a missing key."""

    def handler(request):
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=_openai_response(content="ok"))

    client = _make_client(handler)
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_generate_json_parses_response():
    def handler(request):
        return httpx.Response(200, json=_openai_response(content='{"supported": true}'))

    client = _make_client(handler)
    result = await client.generate_json("prompt", schema={"type": "object"})
    assert result == {"supported": True}


@pytest.mark.asyncio
async def test_generate_json_constrains_decoding_to_the_schema():
    """The schema must reach Ollama as a `json_schema` response_format, not as
    prose in the prompt. Under the old prompt-embedded form, small models
    echoed the schema envelope back instead of an instance, and verification
    silently found zero claims in every answer."""
    seen = {}

    def handler(request):
        seen.update(json_mod.loads(request.content))
        return httpx.Response(200, json=_openai_response(content='{"claims": []}'))

    schema = {"type": "object", "properties": {"claims": {"type": "array"}}}
    client = _make_client(handler)
    await client.generate_json("prompt", schema=schema)

    assert seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["schema"] == schema
    # It also stays in the prompt: constrained decoding fixes the shape, but
    # removing the schema from the prompt cost the model task context and
    # measurably worsened its routing choices.
    assert "claims" in seen["messages"][-1]["content"]


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
async def test_describe_image_not_supported_without_vision_model():
    client = OllamaClient(sleep=_noop_sleep)
    assert client.supports_vision is False
    with pytest.raises(LLMUnavailableError):
        await client.describe_image(image_bytes=b"", mime_type="image/png", prompt="describe")


@pytest.mark.asyncio
async def test_describe_image_uses_configured_vision_model():
    captured = {}

    def handler(request):
        assert request.url.path == "/api/chat"
        captured["body"] = json_mod.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "Bilateral infiltrates visible."}})

    client = _make_client(handler, vision_model="qwen2.5vl:7b")
    assert client.supports_vision is True

    result = await client.describe_image(
        image_bytes=_TINY_PNG, mime_type="image/png", prompt="describe this"
    )

    assert result == "Bilateral infiltrates visible."
    assert captured["body"]["model"] == "qwen2.5vl:7b"
    assert captured["body"]["stream"] is False
    message = captured["body"]["messages"][0]
    assert message["content"] == "describe this"
    assert isinstance(message["images"][0], str) and message["images"][0]
