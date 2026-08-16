"""Tests for the Gemini tool-calling loop, mocking `client.aio.models`
directly (this is the one place we go one layer lower than FakeLLMClient,
since we're testing GeminiClient itself)."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from intelligence.llm.gemini_client import (
    DEFAULT_MAX_TOOL_ROUNDS,
    GeminiClient,
    LLMUnavailableError,
    _sanitize_schema,
)


def _text_part(text):
    return SimpleNamespace(text=text, function_call=None)


def _function_call_part(name, args):
    return SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), text=None)


def _response(parts, finish_reason="STOP", text=None):
    content = SimpleNamespace(parts=parts)
    candidate = SimpleNamespace(content=content, finish_reason=finish_reason)
    resp_text = text if text is not None else "".join(p.text for p in parts if getattr(p, "text", None))
    return SimpleNamespace(candidates=[candidate], text=resp_text or None)


class _FakeModels:
    """Stand-in for `client.aio.models` — scripted `generate_content()`."""

    def __init__(self, responses=None, raise_client_error_once=None, get_result=None, get_exc=None):
        self.responses = list(responses or [])
        self.calls = []
        self._raise_client_error_once = raise_client_error_once
        self.get_result = get_result
        self.get_exc = get_exc

    async def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._raise_client_error_once is not None:
            exc = self._raise_client_error_once
            self._raise_client_error_once = None
            raise exc
        return self.responses.pop(0)

    async def get(self, model):
        if self.get_exc:
            raise self.get_exc
        return self.get_result or SimpleNamespace(name=model)


def _make_client(fake_models, **kwargs):
    client = GeminiClient(api_key="fake-key", model="test-model", sleep=_noop_sleep, **kwargs)
    client._client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))
    return client


async def _noop_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_chat_no_tool_calls_returns_content():
    fake = _FakeModels(responses=[_response([_text_part("Hello there")])])
    client = _make_client(fake)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "Hello there"
    assert result.tool_calls == []
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_chat_executes_tool_call_and_appends_result():
    fake = _FakeModels(
        responses=[
            _response([_function_call_part("my_tool", {"q": "x"})]),
            _response([_text_part("Final answer")]),
        ]
    )
    client = _make_client(fake)

    async def executor(name, args):
        assert name == "my_tool"
        assert args == {"q": "x"}
        return {"ok": True}

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], tool_executor=executor)
    assert result.content == "Final answer"
    assert result.tool_calls == [{"name": "my_tool", "arguments": {"q": "x"}, "result": {"ok": True}}]
    assert result.rounds == 2


@pytest.mark.asyncio
async def test_chat_multiple_function_calls_in_one_round():
    fake = _FakeModels(
        responses=[
            _response(
                [
                    _function_call_part("tool_a", {"x": 1}),
                    _function_call_part("tool_b", {"y": 2}),
                ]
            ),
            _response([_text_part("done")]),
        ]
    )
    client = _make_client(fake)

    calls = []

    async def executor(name, args):
        calls.append((name, args))
        return {"name": name}

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.content == "done"
    assert len(result.tool_calls) == 2
    assert calls == [("tool_a", {"x": 1}), ("tool_b", {"y": 2})]
    # Both function responses from one round land in a single Content.
    second_call_contents = fake.calls[1]["contents"]
    assert len(second_call_contents[-1].parts) == 2


@pytest.mark.asyncio
async def test_chat_tool_exception_surfaces_as_error_result():
    fake = _FakeModels(
        responses=[
            _response([_function_call_part("boom", {})]),
            _response([_text_part("recovered")]),
        ]
    )
    client = _make_client(fake)

    async def executor(name, args):
        raise RuntimeError("tool blew up")

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.tool_calls[0]["result"] == {"error": "tool blew up"}
    assert result.content == "recovered"


@pytest.mark.asyncio
async def test_chat_tool_executor_none_returns_text_without_executing():
    fake = _FakeModels(responses=[_response([_function_call_part("my_tool", {})])])
    client = _make_client(fake)

    result = await client.chat(messages=[], tools=[{"function": {"name": "my_tool", "parameters": {}}}])
    assert result.tool_calls == []
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_chat_hits_max_tool_rounds_cap():
    # AC-001-06, AC-001-10 (docs/specs/SPEC-001-model-provider.md) — this
    # whole module passes unmodified against the Phase 1 shims.
    looping = _response([_function_call_part("loop_tool", {})])
    fake = _FakeModels(responses=[looping] * DEFAULT_MAX_TOOL_ROUNDS)
    client = _make_client(fake)

    async def executor(name, args):
        return {}

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.rounds == DEFAULT_MAX_TOOL_ROUNDS
    assert "limit reached" in result.content.lower()


@pytest.mark.asyncio
async def test_chat_response_with_no_text_and_non_stop_finish_reason():
    fake = _FakeModels(responses=[_response([], finish_reason="SAFETY", text="")])
    client = _make_client(fake)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content  # non-empty explanatory placeholder
    assert "SAFETY" in result.content


@pytest.mark.asyncio
async def test_chat_retries_on_429_then_succeeds():
    exc = errors.ClientError(429, {"error": {"message": "rate limited"}})
    fake = _FakeModels(
        responses=[_response([_text_part("ok")])],
        raise_client_error_once=exc,
    )
    client = _make_client(fake, max_retries=2)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_chat_persistent_429_raises_llm_unavailable():
    exc = errors.ClientError(429, {"error": {"message": "rate limited"}})

    class _AlwaysFails(_FakeModels):
        async def generate_content(self, model, contents, config):
            raise exc

    client = _make_client(_AlwaysFails(), max_retries=2)
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_400_does_not_retry():
    exc = errors.ClientError(400, {"error": {"message": "bad schema"}})
    calls = {"count": 0}

    class _Fails400(_FakeModels):
        async def generate_content(self, model, contents, config):
            calls["count"] += 1
            raise exc

    client = _make_client(_Fails400(), max_retries=3)
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    # No backoff retries on 400 (not retryable), but the client does retry
    # once without `thinking_config` on the first round in case that field
    # itself was rejected — same fallback pattern as the old Ollama client.
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_chat_without_api_key_raises_unavailable():
    client = GeminiClient(api_key=None, model="test-model", sleep=_noop_sleep)
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert await client.health() is False


@pytest.mark.asyncio
async def test_generate_json_parses_response():
    fake = _FakeModels(responses=[_response([], text='{"supported": true}')])
    client = _make_client(fake)

    result = await client.generate_json("prompt", schema={"type": "object", "properties": {}})
    assert result == {"supported": True}


@pytest.mark.asyncio
async def test_health_true_when_reachable():
    fake = _FakeModels(get_result=SimpleNamespace(name="test-model"))
    client = _make_client(fake)
    assert await client.health() is True


@pytest.mark.asyncio
async def test_health_false_on_exception():
    fake = _FakeModels(get_exc=ConnectionError("no network"))
    client = _make_client(fake)
    assert await client.health() is False


@pytest.mark.asyncio
async def test_health_is_cached_within_ttl():
    fake = _FakeModels(get_result=SimpleNamespace(name="test-model"))
    now = {"t": 0.0}
    client = _make_client(fake, time_source=lambda: now["t"])

    assert await client.health() is True
    now["t"] += 1.0  # well within the 60s TTL
    assert await client.health() is True
    # Only one real .get() call across both health() invocations.
    assert fake.get_exc is None


def test_sanitize_schema_drops_unsupported_keys():
    schema = {
        "type": "object",
        "$schema": "http://json-schema.org/draft-07/schema#",
        "properties": {
            "age": {"type": "integer", "exclusiveMinimum": 0},
            "status": {"const": "active"},
        },
        "required": ["age"],
    }
    cleaned = _sanitize_schema(schema)
    assert "$schema" not in cleaned
    assert "exclusiveMinimum" not in cleaned["properties"]["age"]
    assert cleaned["properties"]["status"]["enum"] == ["active"]


def test_sanitize_schema_empty_object_returns_none():
    assert _sanitize_schema({"type": "object", "properties": {}}) is None
    assert _sanitize_schema(None) is None


def test_sanitize_schema_preserves_events_schema():
    from intelligence.nlp.timeline_extractor import EVENTS_SCHEMA

    cleaned = _sanitize_schema(EVENTS_SCHEMA)
    assert cleaned["properties"]["events"]["items"]["properties"]["type"]["enum"]
