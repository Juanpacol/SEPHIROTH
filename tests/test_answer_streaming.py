"""Real token-by-token streaming (AB#67, token streaming) — the executor/
agent/fallback plumbing that forwards a specialist's answering round to the
SSE stream as `answer_delta` events while it is still being generated.

`tests/test_sse_contract.py` covers the wire shape; this file covers the
mechanics: batching, resets on retry, and that the non-streaming paths
(`run_consultation`, a client whose `chat` has no `answer_sink` parameter)
are unaffected.
"""

import asyncio

from sephiroth.models import ChatResult
from sephiroth.runtime.executor import _DeltaBatcher, run_consultation, stream_consultation
from tests.conftest import FakeLLMClient

DRUG_SAFETY_QUERY = "Are these medications safe together?"
EVIDENCE_QUERY = "first-line therapy?"


# --------------------------------------------------------------------------
# stream_consultation / run_consultation, end to end with FakeLLMClient
# --------------------------------------------------------------------------


async def test_stream_yields_deltas_matching_raw_content():
    text = "Metformin remains first-line therapy for type 2 diabetes with CKD."
    client = FakeLLMClient(default_script=[("answer", text)], stream_answers=True)

    events = [e async for e in stream_consultation(client, DRUG_SAFETY_QUERY)]
    kinds = [e["event"] for e in events]

    assert kinds[0] == "routing"
    assert "agent_completed" in kinds
    deltas = [e for e in events if e["event"] == "answer_delta"]
    assert deltas, "expected at least one answer_delta"

    first_completed = kinds.index("agent_completed")
    assert all(kinds[i] != "answer_delta" for i in range(first_completed, len(kinds))), (
        "every answer_delta must come before the first agent_completed"
    )

    # No retry happened, so there is at most one `reset:true` boundary (none
    # here) — every non-reset fragment, concatenated in order, reconstructs
    # the specialist's raw `ChatResult.content` exactly.
    assert all(not d["reset"] for d in deltas)
    assert "".join(d["text"] for d in deltas) == text


async def test_run_consultation_never_receives_a_sink():
    """`run_consultation` (the non-streaming entry point) passes no sink —
    `stream_answers=True` on the double has nothing to stream to, and the
    result is produced exactly as without it."""
    client = FakeLLMClient(default_script=[("answer", "ok")], stream_answers=True)

    result = await run_consultation(client, DRUG_SAFETY_QUERY)

    assert result["final_answer"]
    assert client.chat_calls, "expected at least one chat() call"
    assert all(call.get("answer_sink") is None for call in client.chat_calls)


async def test_final_and_agent_completed_identical_with_and_without_streaming():
    """Turning on `stream_answers` must not change what the frozen `final`/
    `agent_completed` events carry — only additional `answer_delta` events
    appear alongside them."""
    text = "Metformin remains first-line therapy for type 2 diabetes with CKD."

    events_plain = [
        e
        async for e in stream_consultation(
            FakeLLMClient(default_script=[("answer", text)]), DRUG_SAFETY_QUERY
        )
    ]
    events_stream = [
        e
        async for e in stream_consultation(
            FakeLLMClient(default_script=[("answer", text)], stream_answers=True), DRUG_SAFETY_QUERY
        )
    ]

    completed_plain = next(e for e in events_plain if e["event"] == "agent_completed")
    completed_stream = next(e for e in events_stream if e["event"] == "agent_completed")
    assert completed_plain == completed_stream

    final_plain = next(e for e in events_plain if e["event"] == "final")
    final_stream = next(e for e in events_stream if e["event"] == "final")
    # Trace ids/timing are the only thing allowed to differ between runs.
    final_plain.pop("trace")
    final_stream.pop("trace")
    assert final_plain == final_stream


class _ScriptedRoundsClient:
    """A minimal `ModelProvider` double whose `chat()` streams a fixed
    fragment list to `answer_sink` (when given) before returning a
    `ChatResult` with the given `tool_calls` — one scripted round per call,
    used to exercise `_run_specialist`'s retry-then-reset mechanics
    directly (unlike `FakeLLMClient`, which always synthesizes a tool call
    under `tool_choice="required"` and so can never model the omitted-call
    case that triggers a retry here)."""

    model = "fake"
    supports_vision = True
    supports_tools = True

    def __init__(self, rounds):
        self._rounds = list(rounds)
        self.calls = 0

    def describe(self):
        from sephiroth.models import ProviderInfo

        return ProviderInfo(provider="fake", model=self.model, local=True, endpoint="test")

    async def health(self) -> bool:
        return True

    async def generate_json(self, prompt, schema, system_prompt=None):
        return {}

    async def describe_image(self, image_bytes, mime_type, prompt, max_output_tokens=512) -> str:
        return ""

    async def chat(
        self,
        messages,
        system_prompt=None,
        tools=None,
        tool_executor=None,
        think=False,
        tool_choice=None,
        answer_sink=None,
    ) -> ChatResult:
        text, tool_calls = self._rounds[self.calls]
        self.calls += 1
        if answer_sink is not None and text:
            for word in text.split(" "):
                await answer_sink.delta(f"{word} ")
        return ChatResult(
            content=text, tool_calls=list(tool_calls), rounds=1, prompt_tokens=0, completion_tokens=0
        )


def _long_answer(label: str, n: int = 40) -> str:
    """>= the batcher's 32-fragment flush threshold, so each attempt's
    stream auto-flushes at least one batch before `_run_specialist` reacts
    to that attempt's outcome."""
    return " ".join(f"{label}-{i}" for i in range(n))


async def test_retry_after_streamed_text_emits_reset_before_next_attempt():
    """EVIDENCE is `require_tool_call=True`: a round with no tool calls
    makes `Agent.run` raise `ToolCallOmittedError`, which `_run_specialist`
    retries once. A `reset:true` event must separate the discarded
    attempt's deltas from the retry's, and `final.answer` must come from
    the attempt that actually completed."""
    attempt_one = _long_answer("attempt-one")
    attempt_two = _long_answer("attempt-two")
    client = _ScriptedRoundsClient(
        [
            (attempt_one, []),
            (attempt_two, [{"name": "search_clinical_guidelines", "arguments": {}, "result": {}}]),
        ]
    )

    events = [e async for e in stream_consultation(client, EVIDENCE_QUERY)]
    deltas = [e for e in events if e["event"] == "answer_delta"]

    assert client.calls == 2, "expected exactly one retry"
    reset_indices = [i for i, d in enumerate(deltas) if d["reset"]]
    assert len(reset_indices) == 1, f"expected exactly one reset event, got {deltas}"
    reset_at = reset_indices[0]

    before = "".join(d["text"] for d in deltas[:reset_at])
    after = "".join(d["text"] for d in deltas[reset_at + 1 :])
    assert "attempt-one" in before
    assert "attempt-two" not in before
    assert "attempt-two" in after
    assert "attempt-one" not in after

    final = next(e for e in events if e["event"] == "final")
    assert "attempt-two" in final["answer"]
    assert "attempt-one" not in final["answer"]


async def test_exhausted_retries_after_streaming_ends_with_reset():
    """Both attempts omit the tool call — retries exhaust at
    `MAX_AGENT_ATTEMPTS=2`, and the specialist contributes an empty section
    (today's abstain-cleanly behavior, `tests/test_runtime_executor.py`).
    The last delta event on the wire must be the give-up `reset:true`, and
    `final.answer` carries `AbstentionReason.AGENT_FAILURE`'s honest message
    — not an empty string, which previously read as "no evidence" to the
    user when the real cause was the specialist failing (confirmed live)."""
    client = _ScriptedRoundsClient([(_long_answer("try-one"), []), (_long_answer("try-two"), [])])

    events = [e async for e in stream_consultation(client, EVIDENCE_QUERY)]
    deltas = [e for e in events if e["event"] == "answer_delta"]

    assert client.calls == 2
    assert deltas, "expected at least one flushed batch before the final reset"
    assert deltas[-1]["reset"] is True
    assert deltas[-1]["text"] == ""

    final = next(e for e in events if e["event"] == "final")
    assert final["answer"] != ""
    assert final["abstention"]["reason"] == "agent_failure"


class _NoSinkParamClient:
    """A `chat()` with no `answer_sink` parameter and no `**kwargs` catch-
    all — the oldest possible shape of the contract. `Agent.run` must never
    pass the keyword when no sink was requested, or this raises
    `TypeError` instead of completing normally."""

    model = "fake"
    supports_vision = False
    supports_tools = True

    def describe(self):
        from sephiroth.models import ProviderInfo

        return ProviderInfo(provider="fake", model=self.model, local=True, endpoint="test")

    async def health(self) -> bool:
        return True

    async def generate_json(self, prompt, schema, system_prompt=None):
        return {}

    async def describe_image(self, image_bytes, mime_type, prompt, max_output_tokens=512) -> str:
        return ""

    async def chat(
        self, messages, system_prompt=None, tools=None, tool_executor=None, think=False, tool_choice=None
    ) -> ChatResult:
        return ChatResult(content="ok", tool_calls=[], rounds=1, prompt_tokens=0, completion_tokens=0)


async def test_run_consultation_works_with_a_chat_that_has_no_answer_sink_parameter():
    client = _NoSinkParamClient()
    result = await run_consultation(client, DRUG_SAFETY_QUERY)
    assert "ok" in result["final_answer"]


# --------------------------------------------------------------------------
# _DeltaBatcher in isolation
# --------------------------------------------------------------------------


def _drain(queue: "asyncio.Queue") -> list:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


async def test_delta_batcher_flushes_in_batches_of_max_fragments():
    queue: "asyncio.Queue" = asyncio.Queue()
    batcher = _DeltaBatcher(queue, "evidence")

    for _ in range(70):
        await batcher.delta("x")
    await batcher.flush()

    items = _drain(queue)
    assert [len(item["text"]) for item in items] == [32, 32, 6]
    assert all(item["event"] == "answer_delta" and item["agent"] == "evidence" for item in items)
    assert all(item["reset"] is False for item in items)


async def test_delta_batcher_flushes_on_elapsed_time():
    clock = {"t": 0.0}
    queue: "asyncio.Queue" = asyncio.Queue()
    batcher = _DeltaBatcher(queue, "evidence", clock=lambda: clock["t"])

    await batcher.delta("a")
    assert queue.empty(), "must not flush before max_wait_s has passed"
    clock["t"] += 0.5
    await batcher.delta("b")

    items = _drain(queue)
    assert len(items) == 1
    assert items[0]["text"] == "ab"
    assert items[0]["reset"] is False


async def test_delta_batcher_reset_after_a_flush_enqueues_one_reset_event():
    queue: "asyncio.Queue" = asyncio.Queue()
    batcher = _DeltaBatcher(queue, "evidence", max_fragments=2)

    await batcher.delta("a")
    await batcher.delta("b")  # flushes (2 fragments reached)
    await batcher.reset()

    items = _drain(queue)
    assert len(items) == 2
    assert items[0] == {"event": "answer_delta", "agent": "evidence", "text": "ab", "reset": False}
    assert items[1] == {"event": "answer_delta", "agent": "evidence", "text": "", "reset": True}


async def test_delta_batcher_reset_with_nothing_flushed_enqueues_nothing():
    queue: "asyncio.Queue" = asyncio.Queue()
    batcher = _DeltaBatcher(queue, "evidence")

    await batcher.delta("a")
    await batcher.reset()

    assert queue.empty()
