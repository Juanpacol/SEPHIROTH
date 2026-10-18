"""Which provider and model actually served each model call (AB#14).

Before this, the trace and the logs could only say what the client was
*configured* with. Behind a fallback client that is always the primary, so a run
answered by Groq still read as Gemini, and its cost was priced at Gemini's rates.
These tests pin the replacement: one record per call, written by the leaf
clients, carrying the provider that really answered.

`Leaf` wears the same `@record_llm_call` decorators the real clients wear, over
the scripted `FakeLLMClient`, so the composition under test (`FallbackLLMClient`
over two recorded leaves) is the production one.
"""

import asyncio
import io
import json
import logging

import pytest

from core.logging import KeyValueFormatter
from sephiroth.contracts import ExecutionTrace, LlmCall, RunState
from sephiroth.models.base import LLMUnavailableError, PHINotAllowedError, ProviderInfo, classify_unavailable
from sephiroth.models.call_log import record_llm_call
from sephiroth.models.fallback import FallbackLLMClient
from sephiroth.runtime.executor import run_consultation, stream_consultation
from sephiroth.telemetry import build_trace
from sephiroth.telemetry.context import current_fallback, current_trace_id, llm_run_scope
from tests.conftest import FakeLLMClient

QUOTA = "429 RESOURCE_EXHAUSTED: you exceeded your current quota"


class Leaf(FakeLLMClient):
    """A scripted client that is recorded exactly like Gemini/Groq/Ollama."""

    provider = "gemini"
    model = "gemini-flash-latest"
    vision_model = ""

    def __init__(self, *, fail=None, vision_model="", **kwargs):
        super().__init__(**kwargs)
        self.fail = fail
        self.vision_model = vision_model

    def describe(self):
        return ProviderInfo(provider=self.provider, model=self.model, vision_model=self.vision_model)

    @record_llm_call("chat")
    async def chat(self, messages, system_prompt=None, **kwargs):
        if self.fail:
            raise self.fail
        return await super().chat(messages, system_prompt=system_prompt, **kwargs)

    @record_llm_call("generate_json")
    async def generate_json(self, prompt, schema, *, system_prompt=None):
        if self.fail:
            raise self.fail
        return await super().generate_json(prompt, schema, system_prompt=system_prompt)

    @record_llm_call("describe_image")
    async def describe_image(self, image_bytes, mime_type, prompt, max_output_tokens=512):
        if self.fail:
            raise self.fail
        return "A description."

    @record_llm_call("describe_image_stream")
    async def describe_image_stream(self, image_bytes, mime_type, prompt, max_output_tokens=512):
        if self.fail:
            raise self.fail
        yield "chunk-1 "
        yield "chunk-2"


def gemini(**kwargs):
    return Leaf(**kwargs)


def groq(**kwargs):
    leaf = Leaf(**kwargs)
    leaf.provider, leaf.model = "groq", "llama-3.3-70b-versatile"
    return leaf


def exhausted():
    return LLMUnavailableError(QUOTA)


async def chat(client, prompt="hello"):
    return await client.chat([{"role": "user", "content": prompt}], system_prompt="sys")


@pytest.fixture
def log_text():
    """What the platform's formatter would write, as one string per line."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(KeyValueFormatter())
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lambda: [line for line in stream.getvalue().splitlines() if line]
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


class TestReasonCodes:
    @pytest.mark.parametrize(
        "message, reason",
        [
            ("GEMINI_API_KEY is not configured.", "no_api_key"),
            ('401: {"error": {"message": "Invalid API Key"}}', "auth_error"),
            ("400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key.", "auth_error"),
            ("403 PERMISSION_DENIED: the caller does not have permission", "auth_error"),
            (QUOTA, "rate_limited"),
            ('429: {"error": "Rate limit reached for model"}', "rate_limited"),
            ("503 UNAVAILABLE. The model is overloaded", "server_error"),
            ("500: boom", "server_error"),
            ("Could not reach Ollama at http://x — is `ollama serve` running?", "unreachable"),
            ("ReadTimeout: timed out", "timeout"),
            ("GroqClient has no vision_model configured; use Gemini", "no_vision_support"),
            ("Model 'q' not found on this Ollama server", "model_not_found"),
            # "generate" must not be read as "rate".
            ("failed to generate content", "unavailable"),
            ("something nobody anticipated", "unavailable"),
        ],
    )
    def test_the_provider_message_becomes_a_stable_code(self, message, reason):
        assert classify_unavailable(LLMUnavailableError(message)) == reason

    def test_a_privacy_refusal_has_its_own_code(self):
        assert classify_unavailable(PHINotAllowedError("blocked")) == "phi_not_allowed"


class TestEveryCallIsRecorded:
    async def test_a_chat_carries_provider_model_and_real_usage(self):
        client = gemini(default_script=[("answer", "hi")], prompt_tokens=12, completion_tokens=5)

        with llm_run_scope("t1") as calls:
            await chat(client)

        assert len(calls) == 1
        call = calls[0]
        assert (call.kind, call.provider, call.model, call.ok) == (
            "chat",
            "gemini",
            "gemini-flash-latest",
            True,
        )
        assert (call.prompt_tokens, call.completion_tokens) == (12, 5)
        assert call.fallback is False
        assert call.duration_ms >= 0

    async def test_generate_json_is_recorded_too_with_no_usage_reported(self):
        with llm_run_scope("t1") as calls:
            await gemini().generate_json("p", {"type": "object"})

        assert [(c.kind, c.provider, c.prompt_tokens) for c in calls] == [("generate_json", "gemini", 0)]

    async def test_a_vision_call_is_attributed_to_the_vision_model(self):
        client = gemini(vision_model="gemini-vision-x")

        with llm_run_scope("t1") as calls:
            await client.describe_image(b"img", "image/png", "describe")

        assert (calls[0].kind, calls[0].model) == ("describe_image", "gemini-vision-x")

    async def test_a_stream_is_one_record_written_when_it_ends(self):
        with llm_run_scope("t1") as calls:
            chunks = [c async for c in gemini().describe_image_stream(b"img", "image/png", "describe")]

        assert chunks == ["chunk-1 ", "chunk-2"]
        assert [(c.kind, c.ok) for c in calls] == [("describe_image_stream", True)]

    async def test_a_consumer_that_stops_reading_is_not_a_failure(self):
        with llm_run_scope("t1") as calls:
            stream = gemini().describe_image_stream(b"img", "image/png", "describe")
            await stream.__anext__()
            await stream.aclose()

        assert [(c.kind, c.ok, c.error) for c in calls] == [("describe_image_stream", True, "")]

    async def test_a_failure_is_recorded_with_a_code_and_still_propagates(self):
        with llm_run_scope("t1") as calls:
            with pytest.raises(LLMUnavailableError, match="quota"):
                await chat(gemini(fail=exhausted()))

        assert [(c.ok, c.error) for c in calls] == [(False, "rate_limited")]

    async def test_outside_a_run_nothing_is_collected_and_nothing_breaks(self):
        client = gemini(default_script=[("answer", "hi")])

        result = await chat(client)

        assert result.content == "hi"
        assert current_trace_id() == ""

    async def test_the_scope_is_cleared_when_the_run_ends(self):
        with llm_run_scope("t1"):
            assert current_trace_id() == "t1"

        assert current_trace_id() == ""
        assert current_fallback() is None


class TestTheFallbackIsRecordedAsTheProviderThatAnswered:
    async def test_a_healthy_primary_answers_alone(self):
        client = FallbackLLMClient(gemini(default_script=[("answer", "from gemini")]), groq())

        with llm_run_scope("t1") as calls:
            result = await chat(client)

        assert result.content == "from gemini"
        assert [(c.provider, c.fallback, c.ok) for c in calls] == [("gemini", False, True)]

    async def test_when_the_primary_fails_the_secondary_is_recorded_as_the_fallback(self):
        primary = gemini(fail=exhausted())
        secondary = groq(default_script=[("answer", "from groq")], prompt_tokens=100, completion_tokens=20)

        with llm_run_scope("t1") as calls:
            result = await chat(FallbackLLMClient(primary, secondary))

        assert result.content == "from groq"
        assert [(c.provider, c.ok, c.error, c.fallback) for c in calls] == [
            ("gemini", False, "rate_limited", False),
            ("groq", True, "", True),
        ]
        answered = calls[1]
        assert answered.model == "llama-3.3-70b-versatile"
        assert (answered.fallback_from, answered.fallback_reason) == ("gemini", "rate_limited")
        assert (answered.prompt_tokens, answered.completion_tokens) == (100, 20)

    async def test_when_both_fail_both_failures_are_recorded(self):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq(fail=LLMUnavailableError("503 down")))

        with llm_run_scope("t1") as calls:
            with pytest.raises(LLMUnavailableError):
                await chat(client)

        assert [(c.provider, c.error, c.fallback) for c in calls] == [
            ("gemini", "rate_limited", False),
            ("groq", "server_error", True),
        ]

    async def test_the_fallback_marker_does_not_leak_into_the_next_call(self):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq(default_script=[("answer", "x")]))

        with llm_run_scope("t1") as calls:
            await chat(client)
            assert current_fallback() is None
            await FallbackLLMClient(gemini(), groq()).generate_json("p", {})

        assert calls[-1].fallback is False and calls[-1].provider == "gemini"

    async def test_each_call_of_one_run_can_fall_back_on_its_own(self):
        """The answer and the verification are separate calls: one can be
        served by Gemini and the other by Groq in the same consultation."""
        primary = gemini(default_script=[("answer", "answer from gemini")])
        client = FallbackLLMClient(primary, groq())

        with llm_run_scope("t1") as calls:
            await chat(client)
            primary.fail = exhausted()
            await client.generate_json("verify", {"type": "object"})

        assert [(c.kind, c.provider, c.fallback, c.ok) for c in calls] == [
            ("chat", "gemini", False, True),
            ("generate_json", "gemini", False, False),
            ("generate_json", "groq", True, True),
        ]

    async def test_vision_falls_back_too(self):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq())

        with llm_run_scope("t1") as calls:
            text = await client.describe_image(b"img", "image/png", "describe")

        assert text == "A description."
        assert [(c.kind, c.provider, c.fallback) for c in calls] == [
            ("describe_image", "gemini", False),
            ("describe_image", "groq", True),
        ]

    async def test_a_stream_that_fails_before_any_chunk_falls_back(self):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq())

        with llm_run_scope("t1") as calls:
            chunks = [c async for c in client.describe_image_stream(b"img", "image/png", "describe")]

        assert chunks == ["chunk-1 ", "chunk-2"]
        assert [(c.kind, c.provider, c.fallback) for c in calls] == [
            ("describe_image_stream", "gemini", False),
            ("describe_image_stream", "groq", True),
        ]
        assert current_fallback() is None


class TestTheLogLines:
    async def test_every_model_call_line_names_provider_model_fallback_and_trace(self, log_text):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq(default_script=[("answer", "ok")]))

        with llm_run_scope("trace-abc"):
            await chat(client)

        llm_lines = [line for line in log_text() if " llm=" in line]
        assert len(llm_lines) == 2
        for line in llm_lines:
            for key in ("provider=", "model=", "fallback=", "status=", "trace_id=trace-abc"):
                assert key in line, (key, line)
        failed, answered = llm_lines
        assert "provider=gemini" in failed and "fallback=false" in failed and "reason=rate_limited" in failed
        assert "provider=groq" in answered and "fallback=true" in answered
        assert "fallback_from=gemini" in answered and "fallback_reason=rate_limited" in answered

    async def test_the_fallback_warning_keeps_its_wording_and_gains_the_reason_and_trace(self, log_text):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq(default_script=[("answer", "ok")]))

        with llm_run_scope("trace-abc"):
            await chat(client)

        warning = next(line for line in log_text() if "falling back to secondary" in line)
        assert "level=WARNING" in warning
        assert "primary LLM (gemini-flash-latest) unavailable" in warning
        assert "from_provider=gemini" in warning and "reason=rate_limited" in warning
        assert "trace_id=trace-abc" in warning

    async def test_a_call_outside_a_run_is_still_logged_just_without_a_trace(self, log_text):
        await chat(gemini(default_script=[("answer", "ok")]))

        line = next(line for line in log_text() if " llm=" in line)
        assert "provider=gemini" in line and "trace_id" not in line

    async def test_no_prompt_answer_or_provider_text_reaches_the_new_lines_or_records(self, log_text):
        secret_error = LLMUnavailableError("429 quota exceeded: SECRET-PROVIDER-TEXT")
        client = FallbackLLMClient(
            gemini(fail=secret_error),
            groq(default_script=[("answer", "SECRET-ANSWER")]),
        )

        with llm_run_scope("t1") as calls:
            await chat(client, prompt="SECRET-PROMPT about a patient")

        model_call_lines = [line for line in log_text() if " llm=" in line]
        recorded = " ".join(call.model_dump_json() for call in calls)
        for secret in ("SECRET-PROMPT", "SECRET-ANSWER", "SECRET-PROVIDER-TEXT"):
            assert all(secret not in line for line in model_call_lines), secret
            assert secret not in recorded, secret


class TestTheTrace:
    @staticmethod
    def call(provider, model, *, kind="chat", ok=True, fallback=False, prompt=0, completion=0):
        return LlmCall(
            kind=kind,
            provider=provider,
            model=model,
            ok=ok,
            fallback=fallback,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )

    def test_with_no_calls_it_behaves_exactly_as_before(self):
        trace = build_trace(
            RunState(trace_id="t", request="q"), model="gemini-flash-latest", provider="gemini"
        )

        assert trace.llm_calls == []
        assert trace.model_versions == {"provider": "gemini", "model": "gemini-flash-latest"}

    def test_the_trace_names_the_provider_that_answered_not_the_configured_primary(self):
        calls = [
            self.call("gemini", "gemini-flash-latest", ok=False),
            self.call("groq", "llama-3.3-70b-versatile", fallback=True, prompt=1000, completion=500),
        ]

        trace = build_trace(RunState(trace_id="t", request="q"), model="gemini-flash-latest", llm_calls=calls)

        assert trace.model_versions == {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "fallback": "true",
        }
        assert [(c.provider, c.ok) for c in trace.llm_calls] == [("gemini", False), ("groq", True)]

    def test_cost_is_priced_per_call_with_the_model_that_served_it(self):
        calls = [
            self.call("gemini", "gemini-flash-latest", ok=False),
            self.call("groq", "llama-3.3-70b-versatile", fallback=True, prompt=1000, completion=500),
        ]

        trace = build_trace(RunState(trace_id="t", request="q"), model="gemini-flash-latest", llm_calls=calls)

        # Groq's rates ($0.59 / $0.79 per million), not Gemini's.
        assert trace.cost_usd == pytest.approx((1000 * 0.59 + 500 * 0.79) / 1_000_000)

    def test_a_mix_of_providers_in_one_run_is_priced_call_by_call(self):
        calls = [
            self.call("gemini", "gemini-flash-latest", prompt=1000, completion=500),
            self.call(
                "groq", "llama-3.3-70b-versatile", kind="chat", prompt=1000, completion=500, fallback=True
            ),
        ]

        trace = build_trace(RunState(trace_id="t", request="q"), llm_calls=calls)

        expected = (1000 * 0.10 + 500 * 0.40 + 1000 * 0.59 + 500 * 0.79) / 1_000_000
        assert trace.cost_usd == pytest.approx(expected)

    def test_the_answer_is_the_last_good_chat_not_a_later_verification_call(self):
        calls = [
            self.call("groq", "llama-3.3-70b-versatile", fallback=True),
            self.call("gemini", "gemini-flash-latest", kind="generate_json"),
        ]

        trace = build_trace(RunState(trace_id="t", request="q"), llm_calls=calls)

        assert trace.model_versions["provider"] == "groq"

    def test_a_trace_stored_before_this_field_existed_still_loads(self):
        old = {"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", "request": "q"}

        assert ExecutionTrace.model_validate(old).llm_calls == []

    def test_the_calls_survive_the_json_round_trip_the_database_does(self):
        calls = [self.call("groq", "llama-3.3-70b-versatile", fallback=True)]
        trace = build_trace(RunState(trace_id="t", request="q"), llm_calls=calls)

        stored = json.loads(trace.model_dump_json())

        assert ExecutionTrace.model_validate(stored).llm_calls == trace.llm_calls

    def test_a_call_record_refuses_unknown_fields_so_content_cannot_slip_in(self):
        with pytest.raises(ValueError):
            LlmCall(kind="chat", provider="x", model="y", prompt="the patient says ...")  # type: ignore[call-arg]


class TestTheWholeConsultation:
    async def test_a_run_answered_by_the_fallback_says_so_in_its_trace(self):
        client = FallbackLLMClient(
            gemini(fail=exhausted()),
            groq(default_script=[("answer", "A plain answer.")], prompt_tokens=1000, completion_tokens=500),
        )

        state = await run_consultation(client, "test query")
        trace = state["trace"]

        assert state["final_answer"].startswith("A plain answer.")
        assert trace["model_versions"] == {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "fallback": "true",
        }
        chats = [c for c in trace["llm_calls"] if c["kind"] == "chat"]
        assert [(c["provider"], c["ok"], c["fallback"]) for c in chats] == [
            ("gemini", False, False),
            ("groq", True, True),
        ]
        # Groq's price for 1000 + 500 tokens, not Gemini's.
        assert trace["cost_usd"] == pytest.approx((1000 * 0.59 + 500 * 0.79) / 1_000_000)

    async def test_a_run_served_only_by_the_primary_records_no_fallback(self):
        client = FallbackLLMClient(gemini(default_script=[("answer", "From gemini.")]), groq())

        trace = (await run_consultation(client, "test query"))["trace"]

        assert trace["model_versions"] == {"provider": "gemini", "model": "gemini-flash-latest"}
        assert not any(c["fallback"] for c in trace["llm_calls"])

    async def test_a_rejected_query_makes_no_model_call_and_the_trace_says_so(self):
        client = FallbackLLMClient(gemini(), groq())

        state = await run_consultation(
            client, "What do the guidelines recommend for filing quarterly small-business tax returns?"
        )

        assert state["abstention"]["reason"] == "out_of_scope"
        assert state["trace"]["llm_calls"] == []

    async def test_every_log_line_of_the_run_carries_its_trace_id(self, log_text):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq(default_script=[("answer", "ok")]))

        state = await run_consultation(client, "test query")

        trace_id = state["trace"]["trace_id"]
        model_call_lines = [line for line in log_text() if " llm=" in line]
        assert model_call_lines, "the run made model calls but none were logged"
        assert all(f"trace_id={trace_id}" in line for line in model_call_lines)

    async def test_the_streaming_run_records_its_calls_and_clears_its_scope(self):
        client = FallbackLLMClient(gemini(fail=exhausted()), groq(default_script=[("answer", "Streamed.")]))

        events = [event async for event in stream_consultation(client, "test query")]
        final = next(event for event in events if event["event"] == "final")

        assert any(c["provider"] == "groq" and c["fallback"] for c in final["trace"]["llm_calls"])
        assert current_trace_id() == ""

    async def test_concurrent_runs_never_see_each_others_calls(self):
        falling_back = FallbackLLMClient(gemini(fail=exhausted()), groq(default_script=[("answer", "one")]))
        healthy = FallbackLLMClient(gemini(default_script=[("answer", "two")]), groq())

        first, second = await asyncio.gather(
            run_consultation(falling_back, "test query"),
            run_consultation(healthy, "test query"),
        )

        assert first["trace"]["trace_id"] != second["trace"]["trace_id"]
        assert {c["provider"] for c in first["trace"]["llm_calls"]} == {"gemini", "groq"}
        assert {c["provider"] for c in second["trace"]["llm_calls"]} == {"gemini"}
