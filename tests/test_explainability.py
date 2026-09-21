"""SPEC-029 AC-029-06 / B-3: removing `laboratory`/`coordinator` as live
agents MUST NOT degrade `explanation` for consultations persisted before
this phase (`docs/00-migration-charter.md` §2.3, "explanation is derived,
never stored"). `_NO_TOOL_ACTIONS` keeps both entries permanently even
though no live consultation can produce those agent names going forward.
"""

from sephiroth.telemetry.explain import build_explanation


def test_historical_laboratory_step_still_renders():
    explanation = build_explanation(agents=["laboratory"], tool_calls=[], citation_report={})
    steps = explanation["steps"]
    assert len(steps) == 1
    assert steps[0]["agent"] == "laboratory"
    assert steps[0]["action"] == "Interpreted the lab values in the patient context"


def test_historical_coordinator_step_still_renders():
    explanation = build_explanation(agents=["coordinator"], tool_calls=[], citation_report={})
    steps = explanation["steps"]
    assert len(steps) == 1
    assert steps[0]["agent"] == "coordinator"
    assert steps[0]["action"] == "Synthesized the specialist analyses into the final answer"


def test_historical_multi_agent_consultation_still_renders_every_agent():
    """A pre-consolidation consultation could name up to five agents at
    once (the fan-out plus the coordinator) — reconstructing its
    explanation must not choke on any of them."""
    explanation = build_explanation(
        agents=["radiology", "laboratory", "drug_safety", "evidence", "coordinator"],
        tool_calls=[{"agent": "radiology", "name": "describe_medical_image", "arguments": {}}],
        citation_report={},
    )
    rendered_agents = {step["agent"] for step in explanation["steps"]}
    assert rendered_agents == {"radiology", "laboratory", "drug_safety", "evidence", "coordinator"}
