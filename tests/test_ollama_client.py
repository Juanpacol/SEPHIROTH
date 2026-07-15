"""Tests for the Ollama tool-calling loop, mocking `ollama.AsyncClient`
directly (this is the one place we go one layer lower than FakeOllamaClient,
since we're testing OllamaClient itself)."""

import ollama
import pytest

from intelligence.llm.ollama_client import MAX_TOOL_ROUNDS, OllamaClient


class _FakeAsyncClient:
    """Stand-in for `ollama.AsyncClient` — scripted `.chat()` responses."""

    def __init__(self, responses=None, list_response=None, raise_response_error_once=False):
        self.responses = list(responses or [])
        self.list_response = list_response or {"models": []}
        self.calls = []
        self._raised_once = not raise_response_error_once

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if not self._raised_once:
            self._raised_once = True
            raise ollama.ResponseError("no think support", 400)
        return self.responses.pop(0)

    async def list(self):
        return self.list_response


def _make_client(monkeypatch, fake):
    client = OllamaClient(host="http://fake", model="test-model")
    monkeypatch.setattr(client, "_client", fake)
    return client


@pytest.mark.asyncio
async def test_chat_no_tool_calls_returns_content(monkeypatch):
    fake = _FakeAsyncClient(responses=[{"message": {"content": "Hello there", "tool_calls": []}}])
    client = _make_client(monkeypatch, fake)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "Hello there"
    assert result.tool_calls == []
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_chat_executes_tool_call_and_appends_result(monkeypatch):
    fake = _FakeAsyncClient(
        responses=[
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "my_tool", "arguments": {"q": "x"}}}],
                }
            },
            {"message": {"content": "Final answer", "tool_calls": []}},
        ]
    )
    client = _make_client(monkeypatch, fake)

    async def executor(name, args):
        assert name == "my_tool"
        assert args == {"q": "x"}
        return {"ok": True}

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], tool_executor=executor)
    assert result.content == "Final answer"
    assert result.tool_calls == [{"name": "my_tool", "arguments": {"q": "x"}, "result": {"ok": True}}]
    assert result.rounds == 2


@pytest.mark.asyncio
async def test_chat_string_encoded_arguments_are_parsed(monkeypatch):
    import json as json_mod

    fake = _FakeAsyncClient(
        responses=[
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "my_tool",
                                "arguments": json_mod.dumps({"q": "x"}),
                            }
                        }
                    ],
                }
            },
            {"message": {"content": "done", "tool_calls": []}},
        ]
    )
    client = _make_client(monkeypatch, fake)

    async def executor(name, args):
        assert args == {"q": "x"}
        return "ok"

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.content == "done"


@pytest.mark.asyncio
async def test_chat_tool_exception_surfaces_as_error_result(monkeypatch):
    fake = _FakeAsyncClient(
        responses=[
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "boom", "arguments": {}}}],
                }
            },
            {"message": {"content": "recovered", "tool_calls": []}},
        ]
    )
    client = _make_client(monkeypatch, fake)

    async def executor(name, args):
        raise RuntimeError("tool blew up")

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.tool_calls[0]["result"] == {"error": "tool blew up"}
    assert result.content == "recovered"


@pytest.mark.asyncio
async def test_chat_hits_max_tool_rounds_cap(monkeypatch):
    looping_response = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {"name": "loop_tool", "arguments": {}}}],
        }
    }
    fake = _FakeAsyncClient(responses=[looping_response] * MAX_TOOL_ROUNDS)
    client = _make_client(monkeypatch, fake)

    async def executor(name, args):
        return {}

    result = await client.chat(messages=[], tool_executor=executor)
    assert result.rounds == MAX_TOOL_ROUNDS
    assert "limit reached" in result.content.lower()


@pytest.mark.asyncio
async def test_chat_retries_without_think_on_response_error(monkeypatch):
    fake = _FakeAsyncClient(
        responses=[{"message": {"content": "ok", "tool_calls": []}}],
        raise_response_error_once=True,
    )
    client = _make_client(monkeypatch, fake)

    result = await client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_generate_json_parses_response(monkeypatch):
    import json as json_mod

    fake = _FakeAsyncClient(responses=[{"message": {"content": json_mod.dumps({"supported": True})}}])
    client = _make_client(monkeypatch, fake)

    result = await client.generate_json("prompt", schema={"type": "object"})
    assert result == {"supported": True}


@pytest.mark.asyncio
async def test_health_true_when_model_present(monkeypatch):
    fake = _FakeAsyncClient(list_response={"models": [{"model": "test-model:latest"}]})
    client = _make_client(monkeypatch, fake)
    assert await client.health() is True


@pytest.mark.asyncio
async def test_health_false_on_exception(monkeypatch):
    class _Boom:
        async def list(self):
            raise ConnectionError("no server")

    client = _make_client(monkeypatch, _Boom())
    assert await client.health() is False


@pytest.mark.asyncio
async def test_health_false_when_model_absent(monkeypatch):
    fake = _FakeAsyncClient(list_response={"models": [{"model": "other-model:latest"}]})
    client = _make_client(monkeypatch, fake)
    assert await client.health() is False
