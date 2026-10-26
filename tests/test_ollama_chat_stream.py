"""`OllamaClient.chat(answer_sink=...)` — native `/api/chat` token streaming
(AB#67). Reuses `test_ollama_client.py`'s `httpx.MockTransport` pattern; the
NDJSON parsing itself mirrors `describe_image_stream` (ollama.py:391-432).
"""

import json as json_mod

import httpx
import pytest

from sephiroth.models import LLMUnavailableError
from sephiroth.models.ollama import OllamaClient


async def _noop_sleep(_seconds):
    return None


def _make_client(handler, base_url="http://localhost:11434/v1", **kwargs):
    client = OllamaClient(sleep=_noop_sleep, **kwargs)
    client.base_url = base_url
    client._client = httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handler))
    return client


def _ndjson(*lines) -> bytes:
    return "".join(json_mod.dumps(line) + "\n" for line in lines).encode()


class _CollectingSink:
    def __init__(self):
        self.deltas: list[str] = []
        self.resets = 0

    async def delta(self, text: str) -> None:
        self.deltas.append(text)

    async def reset(self) -> None:
        self.resets += 1


class _FlakyStream(httpx.AsyncByteStream):
    """Yields a fixed set of chunks, then raises — simulates a connection
    dropping partway through a stream (test plan item 4)."""

    def __init__(self, chunks: list[bytes], exc: Exception):
        self._chunks = chunks
        self._exc = exc

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk
        raise self._exc

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_stream_yields_fragments_in_order_and_sums_done_chunk_tokens():
    body = _ndjson(
        {"message": {"role": "assistant", "content": "Hello "}, "done": False},
        {"message": {"role": "assistant", "content": "there"}, "done": False},
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "prompt_eval_count": 11,
            "eval_count": 7,
        },
    )
    captured = {}

    def handler(request):
        captured["body"] = json_mod.loads(request.content)
        return httpx.Response(200, content=body)

    client = _make_client(handler)
    sink = _CollectingSink()

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], answer_sink=sink)

    assert sink.deltas == ["Hello ", "there"]
    assert result.content == "Hello there"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 7
    assert captured["body"]["stream"] is True
    assert sink.resets == 0


@pytest.mark.asyncio
async def test_tool_calls_in_a_single_chunk_reset_before_round_two():
    calls = {"n": 0}
    round_one = _ndjson(
        {"message": {"role": "assistant", "content": "checking "}, "done": False},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "my_tool", "arguments": {"q": "x"}}}],
            },
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 3,
        },
    )
    round_two = _ndjson(
        {"message": {"role": "assistant", "content": "Final "}, "done": False},
        {"message": {"role": "assistant", "content": "answer"}, "done": True},
    )

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=round_one if calls["n"] == 1 else round_two)

    client = _make_client(handler)
    sink = _CollectingSink()

    async def executor(name, args):
        assert name == "my_tool"
        assert args == {"q": "x"}
        return {"ok": True}

    result = await client.chat(
        messages=[{"role": "user", "content": "hi"}], answer_sink=sink, tool_executor=executor
    )

    assert result.content == "Final answer"
    assert result.tool_calls == [{"name": "my_tool", "arguments": {"q": "x"}, "result": {"ok": True}}]
    assert sink.resets == 1
    assert sink.deltas == ["checking ", "Final ", "answer"]


@pytest.mark.asyncio
async def test_tool_calls_split_across_chunks_reset_once():
    calls = {"n": 0}
    # Ollama can emit `tool_calls` progressively across more than one chunk
    # before `done` — `_post_stream` must accumulate all of them and still
    # reset exactly once, not once per chunk that carried a fragment.
    round_one = _ndjson(
        {"message": {"role": "assistant", "content": "checking "}, "done": False},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "my_tool", "arguments": {}}}],
            },
            "done": False,
        },
        {"message": {"role": "assistant", "content": ""}, "done": True},
    )
    round_two = _ndjson({"message": {"role": "assistant", "content": "done"}, "done": True})

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=round_one if calls["n"] == 1 else round_two)

    client = _make_client(handler)
    sink = _CollectingSink()

    async def executor(name, args):
        return {}

    result = await client.chat(messages=[], answer_sink=sink, tool_executor=executor)

    assert result.tool_calls == [{"name": "my_tool", "arguments": {}, "result": {}}]
    assert sink.resets == 1
    assert sink.deltas == ["checking ", "done"]


@pytest.mark.asyncio
async def test_a_503_before_any_fragment_is_retried_and_succeeds():
    calls = {"n": 0}
    body = _ndjson({"message": {"role": "assistant", "content": "ok"}, "done": True})

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, content=body)

    client = _make_client(handler, max_retries=2)
    sink = _CollectingSink()

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], answer_sink=sink)

    assert result.content == "ok"
    assert sink.deltas == ["ok"], "the sink must never see a duplicate from the retried attempt"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_connection_error_after_first_fragment_raises_with_no_retry():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(
            200,
            stream=_FlakyStream(
                [json_mod.dumps({"message": {"content": "partial "}, "done": False}).encode() + b"\n"],
                httpx.ReadError("dropped"),
            ),
        )

    client = _make_client(handler, max_retries=3)
    sink = _CollectingSink()

    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "hi"}], answer_sink=sink)

    assert sink.deltas == ["partial "]
    assert calls["n"] == 1, "no retry once a fragment has already reached the sink"


@pytest.mark.asyncio
async def test_no_sink_keeps_stream_false():
    captured = {}

    def handler(request):
        captured["body"] = json_mod.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}, "done": True})

    client = _make_client(handler)
    result = await client.chat(messages=[{"role": "user", "content": "hi"}])

    assert captured["body"]["stream"] is False
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_non_local_base_url_with_sink_uses_non_native_path_with_no_sink_calls():
    captured = {}

    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        captured["body"] = json_mod.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    client = _make_client(handler, base_url="https://openrouter.ai/api/v1")
    sink = _CollectingSink()

    result = await client.chat(messages=[{"role": "user", "content": "hi"}], answer_sink=sink)

    assert result.content == "ok"
    assert sink.deltas == []
    assert "stream" not in captured["body"]
