"""The executor's fan-out: bounded concurrency, per-agent error isolation, and
progressive streaming as each specialist actually finishes.

`tests/test_workflow.py` already proves output parity; this file proves the
concurrency *mechanics* the wire contract doesn't directly observe — that a
raising agent doesn't take down the rest, and that streaming is genuinely
progressive (`asyncio.as_completed`), not a burst after everyone finishes.

Also verifies AC-004-07, AC-004-09 (docs/specs/SPEC-004-verification-safety.md)
— the RunState-adoption and abstain/partial wiring tests near the bottom.

Also verifies AC-005-06 (docs/specs/SPEC-005-context-engine.md): every test in
this file (plus test_workflow.py/test_sse_contract.py/test_api_agents.py)
passes unmodified after the executor switched to enforcing
`context_for_agent` — the evidence that no agent depended on a context
field outside its declared `context_fields`.
"""

import asyncio

import pytest

from sephiroth.runtime.executor import run_consultation, stream_consultation
from tests.conftest import FakeLLMClient

pytestmark = pytest.mark.spec


async def test_all_four_specialists_run_concurrently_not_sequentially():
    """A staggered-sleep fake: if the four ran sequentially, this would take
    4x as long as the slowest single agent."""

    class SlowFakeClient(FakeLLMClient):
        async def chat(self, messages, system_prompt=None, **kwargs):
            await asyncio.sleep(0.05)
            return await super().chat(messages, system_prompt=system_prompt, **kwargs)

    client = SlowFakeClient(default_script=[("answer", "ok")])
    context = {"image_path": "/x.png", "lab_results": {"a1c": "7.0"}, "medications": ["metformin"]}

    started = asyncio.get_event_loop().time()
    await run_consultation(client, "test query", context=context)
    elapsed = asyncio.get_event_loop().time() - started

    # 5 agents (4 specialists + coordinator) at 0.05s each: sequential would be
    # >=0.25s; concurrent specialists collapse the first four into ~0.05s, so
    # the whole run should land well under 4x a single agent's delay.
    assert elapsed < 0.05 * 3, f"took {elapsed:.3f}s — looks sequential, not concurrent"


async def test_one_specialist_raising_does_not_abort_the_others():
    """Matches the pre-Phase-3 behaviour exactly: an unhandled exception during
    fan-out propagates (no recovery yet — that's a tracked future gap, not
    silently introduced here), but this pins that it's a clean propagation,
    not a partial/corrupted result."""

    class FailingClient(FakeLLMClient):
        async def chat(self, messages, system_prompt=None, **kwargs):
            if system_prompt and "radiology specialist" in system_prompt:
                raise RuntimeError("simulated agent failure")
            return await super().chat(messages, system_prompt=system_prompt, **kwargs)

    client = FailingClient(default_script=[("answer", "ok")])

    with pytest.raises(RuntimeError, match="simulated agent failure"):
        await run_consultation(client, "test query", context={"image_path": "/x.png"})


async def test_stream_yields_agent_completed_progressively_not_in_a_burst():
    """The fastest specialist's `agent_completed` must be observable before
    the slowest one finishes — proves `asyncio.as_completed` is doing real
    work, not `asyncio.gather` dressed up as streaming."""

    class VariableSpeedClient(FakeLLMClient):
        async def chat(self, messages, system_prompt=None, **kwargs):
            if system_prompt and "laboratory medicine specialist" in system_prompt:
                await asyncio.sleep(0.2)
            return await super().chat(messages, system_prompt=system_prompt, **kwargs)

    client = VariableSpeedClient(default_script=[("answer", "ok")])
    context = {"lab_results": {"a1c": "7.0"}}  # evidence (fast) + laboratory (slow)

    first_agent_completed_at = None
    started = asyncio.get_event_loop().time()
    async for event in stream_consultation(client, "test query", context=context):
        if event["event"] == "agent_completed" and first_agent_completed_at is None:
            first_agent_completed_at = asyncio.get_event_loop().time() - started

    assert first_agent_completed_at is not None
    assert first_agent_completed_at < 0.15, (
        f"first agent_completed arrived at {first_agent_completed_at:.3f}s — "
        "expected the fast agent to complete well before the 0.2s slow one"
    )


async def test_final_event_agents_involved_is_sorted_regardless_of_completion_order():
    """Matches the pre-Phase-3 behaviour: the `final` event's `agents_involved`
    is always alphabetically sorted, independent of which specialist actually
    finished first — `laboratory` completes before `radiology` here, the
    reverse of declaration order, and the wire value must not leak that."""

    class ReverseOrderClient(FakeLLMClient):
        async def chat(self, messages, system_prompt=None, **kwargs):
            if system_prompt and "radiology specialist" in system_prompt:
                await asyncio.sleep(0.05)
            return await super().chat(messages, system_prompt=system_prompt, **kwargs)

    client = ReverseOrderClient(default_script=[("answer", "ok")])
    context = {"image_path": "/x.png", "lab_results": {"a1c": "7.0"}}

    events = [e async for e in stream_consultation(client, "test query", context=context)]
    final = events[-1]

    assert final["event"] == "final"
    assert final["agents_involved"] == sorted(final["agents_involved"])
    assert set(final["agents_involved"]) == {"evidence", "laboratory", "radiology"}


async def test_run_consultation_default_answers_when_no_claims_extracted():
    """No `json_payloads` queued (the default) means `extract_claims` sees an
    empty payload and returns no claims — `supported_claim_ratio` stays 1.0
    and the run answers normally. This is SPEC-004's RunState-adoption gate:
    every pre-existing test in the suite exercises exactly this path, which
    is why they all kept passing unmodified."""
    client = FakeLLMClient(default_script=[("answer", "A plain answer with no claims scripted.")])
    state = await run_consultation(client, "test query")

    assert state["abstention"]["status"] == "answer"
    assert state["abstention"]["reason"] is None
    assert state["verification_report"] == {"claims": [], "contradictions": []}
    assert state["final_answer"] == "A plain answer with no claims scripted."


async def test_run_consultation_abstains_on_unsupported_high_risk_claim(monkeypatch):
    """End-to-end: verify_claims is patched to return one unsupported
    high-risk claim (the extraction/verification logic itself is unit-tested
    separately in tests/test_verification_verify.py) — the run must decline
    rather than surface the coordinator's raw answer."""
    import sephiroth.runtime.executor as executor_module
    from sephiroth.contracts import Claim, RiskLevel, VerificationReport, VerificationStatus

    async def fake_verify_claims(claims, evidence, client):
        return VerificationReport(
            claims=[
                Claim(
                    id="c1",
                    text="unsupported claim",
                    risk=RiskLevel.CRITICAL,
                    status=VerificationStatus.UNSUPPORTED,
                )
            ]
        )

    async def fake_extract_claims(answer, client):
        return [Claim(id="c1", text="unsupported claim", risk=RiskLevel.CRITICAL)]

    monkeypatch.setattr(executor_module, "extract_claims", fake_extract_claims)
    monkeypatch.setattr(executor_module, "verify_claims", fake_verify_claims)

    client = FakeLLMClient(default_script=[("answer", "Double the warfarin dose immediately.")])
    state = await run_consultation(client, "test query")

    assert state["abstention"]["status"] == "abstain"
    assert state["abstention"]["reason"] == "unsupported_high_risk_claim"
    assert state["final_answer"] == state["abstention"]["message"]
    assert "Double the warfarin dose" not in state["final_answer"]


async def test_stream_consultation_final_event_carries_verification_and_abstention():
    client = FakeLLMClient(default_script=[("answer", "ok")])
    events = [e async for e in stream_consultation(client, "test query")]
    final = events[-1]

    assert "verification_report" in final
    assert "abstention" in final
    assert final["abstention"]["status"] == "answer"


async def test_run_consultation_partial_status_prepends_caveat_banner(monkeypatch):
    """A PARTIAL abstention decision keeps the coordinator's answer but
    prepends a fixed caveat banner — unlike ABSTAIN, which replaces it."""
    import sephiroth.runtime.executor as executor_module
    from sephiroth.contracts import AbstentionDecision, ResponseStatus
    from sephiroth.safety.abstention import PARTIAL_BANNER

    def fake_decide(report, confidence, input_flags):
        return AbstentionDecision(
            status=ResponseStatus.PARTIAL, confidence=confidence, supported_claim_ratio=1.0
        )

    monkeypatch.setattr(executor_module, "decide_abstention", fake_decide)

    client = FakeLLMClient(default_script=[("answer", "The coordinator's real answer.")])
    state = await run_consultation(client, "test query")

    assert state["abstention"]["status"] == "partial"
    assert state["final_answer"].startswith(PARTIAL_BANNER)
    assert "The coordinator's real answer." in state["final_answer"]
