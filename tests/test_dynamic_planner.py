"""`route_specialists_dynamic` — SPEC-008, closes SPEC-003 NG-1.

Same 4 cases `test_workflow.py` proves for the static `route_specialists`
(image, labs, medications, none) plus degradation cases, exercised via a
scripted `FakeLLMClient` (no live model). The last two tests wire the flag
through `run_consultation`/`stream_consultation` to prove the routing
event itself reflects the dynamic decision, not just the bare function.

Verifies AC-008-01, AC-008-02, AC-008-03 (docs/specs/SPEC-008-dynamic-planner.md).
"""

from core.config import settings
from sephiroth.runtime import route_specialists_dynamic, run_consultation, stream_consultation
from sephiroth.runtime.planner import route_specialists
from tests.conftest import FakeLLMClient


class RaisingClient(FakeLLMClient):
    async def generate_json(self, prompt, schema, system_prompt=None):
        raise RuntimeError("model unavailable")


async def test_dynamic_planner_selects_radiology_for_image():
    client = FakeLLMClient(json_payloads=[{"agents": ["radiology", "evidence"]}])
    result = await route_specialists_dynamic({"image_path": "/x.png"}, client)
    assert result == ["radiology", "evidence"]


async def test_dynamic_planner_selects_laboratory_for_labs():
    client = FakeLLMClient(json_payloads=[{"agents": ["laboratory"]}])
    result = await route_specialists_dynamic({"lab_results": {"a1c": "7.0"}}, client)
    assert result == ["laboratory"]


async def test_dynamic_planner_selects_drug_safety_for_medications():
    client = FakeLLMClient(json_payloads=[{"agents": ["drug_safety", "evidence"]}])
    result = await route_specialists_dynamic({"medications": ["metformin"]}, client)
    assert result == ["drug_safety", "evidence"]


async def test_dynamic_planner_degrades_to_static_when_no_signals_and_empty_agents():
    """Verifies AC-008-02: an empty `agents` list is invalid, not a valid
    "run nothing" decision — falls back to the static heuristic."""
    client = FakeLLMClient(json_payloads=[{"agents": []}])
    result = await route_specialists_dynamic(None, client)
    assert result == route_specialists(None)


async def test_dynamic_planner_filters_unknown_agent_names():
    client = FakeLLMClient(json_payloads=[{"agents": ["radiology", "bogus"]}])
    result = await route_specialists_dynamic({"image_path": "/x.png"}, client)
    assert result == ["radiology"]


async def test_dynamic_planner_degrades_to_static_on_malformed_payload():
    """Verifies AC-008-02: a payload missing the `agents` key falls back."""
    client = FakeLLMClient(json_payloads=[{"not_agents": []}])
    context = {"lab_results": {"a1c": "7.0"}}
    result = await route_specialists_dynamic(context, client)
    assert result == route_specialists(context)


async def test_dynamic_planner_degrades_to_static_on_non_dict_payload():
    """Verifies AC-008-02: a non-dict `generate_json` return (e.g. a bare
    list) falls back — the schema is advisory, not enforced upstream."""
    client = FakeLLMClient(json_payloads=[["radiology"]])
    context = {"image_path": "/x.png"}
    result = await route_specialists_dynamic(context, client)
    assert result == route_specialists(context)


async def test_dynamic_planner_degrades_to_static_on_model_failure():
    """Verifies AC-008-02: a `generate_json` exception never propagates —
    routing must always produce a usable specialist list."""
    client = RaisingClient()
    context = {"medications": ["metformin"]}
    result = await route_specialists_dynamic(context, client)
    assert result == route_specialists(context)


async def test_dynamic_planner_prompt_carries_query_and_conditions():
    """The prompt sent to the model must include the clinician's actual
    question and known conditions, not just the three structured-data
    booleans — otherwise the dynamic planner can't route on domains the
    question mentions in free text (e.g. drug interactions) when no
    matching structured field was populated."""
    from sephiroth.runtime.planner import _routing_prompt

    prompt = _routing_prompt(
        {"conditions": ["type 2 diabetes"]}, query="Check for interactions with metformin"
    )
    assert "Check for interactions with metformin" in prompt
    assert "type 2 diabetes" in prompt


async def test_dynamic_planner_routes_drug_safety_from_free_text_query():
    """No `medications` field is populated, but the question is clearly
    about a drug interaction — the model (scripted here) should still be
    able to pick `drug_safety` since the prompt now carries the query."""
    client = FakeLLMClient(json_payloads=[{"agents": ["drug_safety", "evidence"]}])
    result = await route_specialists_dynamic(
        {"conditions": ["type 2 diabetes"]},
        client,
        query="Are there interactions between metformin and lisinopril?",
    )
    assert result == ["drug_safety", "evidence"]


async def test_dynamic_routing_wired_into_run_consultation(monkeypatch):
    """Verifies AC-008-03: the flag actually changes which agents run."""
    monkeypatch.setattr(settings, "enable_dynamic_planner", True)
    client = FakeLLMClient(
        json_payloads=[{"agents": ["laboratory"]}],
        scripts={
            "laboratory medicine specialist": [("answer", "Potassium within range.")],
            "coordinating physician-assistant": [
                (
                    "answer",
                    "Summary. This is decision support, not a diagnosis — professional review required.",
                )
            ],
        },
    )
    result = await run_consultation(client, "Check labs", context={"lab_results": {"potassium": "4.0"}})
    assert set(result["agent_outputs"].keys()) == {"laboratory"}


async def test_dynamic_routing_wired_into_stream_consultation(monkeypatch):
    """Verifies AC-008-03: the `routing` SSE event carries the dynamic
    decision — same frozen shape (`{"event": "routing", "agents": [...]}`),
    different content than the static heuristic would have produced."""
    monkeypatch.setattr(settings, "enable_dynamic_planner", True)
    client = FakeLLMClient(
        json_payloads=[{"agents": ["evidence"]}],
        scripts={
            "clinical evidence specialist": [("answer", "No strong evidence found.")],
            "coordinating physician-assistant": [
                (
                    "answer",
                    "Summary. This is decision support, not a diagnosis — professional review required.",
                )
            ],
        },
    )
    events = [e async for e in stream_consultation(client, "hi")]
    assert events[0] == {"event": "routing", "agents": ["evidence"]}
