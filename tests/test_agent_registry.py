"""The three `AgentCapability` records match the post-consolidation
registry exactly — same identity, same tools, same node/display name split.

Verifies AC-003-04 (`docs/specs/SPEC-003-agent-runtime.md`) and
AC-029-01/02 (`docs/specs/SPEC-029-agent-consolidation.md` — `laboratory`
and `coordinator` are removed, `SPECIALISTS`/`AGENTS` collapse into one
dict).
"""

import pytest

from sephiroth.runtime.registry import (
    AGENTS,
    DRUG_SAFETY,
    EVIDENCE,
    RADIOLOGY,
    get_capability,
)

pytestmark = pytest.mark.spec

# The exact `allowed_tools` lists from the pre-Phase-3 hardcoded classes
# (intelligence/agents/__init__.py, before this phase), keyed by node name.
LEGACY_ALLOWED_TOOLS = {
    "radiology": ["inspect_medical_image", "analyze_medical_image", "describe_medical_image"],
    "drug_safety": ["check_drug_interactions"],
    "evidence": ["search_clinical_guidelines", "search_pubmed"],
}


@pytest.mark.xfail(
    reason="SPEC-029 not yet implemented — laboratory/coordinator removal lands in SF059", strict=False
)
def test_agents_is_exactly_the_three_specialists_intent_router_selects_from():
    """AC-029-01: `laboratory` and `coordinator` no longer exist as
    registry entries — there is no longer a separate "specialists vs. all
    agents" distinction once there is no coordinator to add on top."""
    assert set(AGENTS) == {"radiology", "drug_safety", "evidence"}


@pytest.mark.parametrize(
    "capability,expected_id,expected_node_name",
    [
        (RADIOLOGY, "radiology", "radiology"),
        (DRUG_SAFETY, "drug-safety", "drug_safety"),
        (EVIDENCE, "evidence", "evidence"),
    ],
)
def test_display_id_and_node_name_match_the_pre_phase_3_split(capability, expected_id, expected_node_name):
    """`drug-safety` (display) vs `drug_safety` (node) predates this phase and
    is load-bearing on the wire (docs/00-migration-charter.md §2.1) — this
    phase must not accidentally unify or swap them."""
    assert capability.id == expected_id
    assert capability.node_name == expected_node_name


@pytest.mark.parametrize("node_name,legacy_tools", LEGACY_ALLOWED_TOOLS.items())
def test_tools_match_the_legacy_allowed_tools_lists(node_name, legacy_tools):
    assert get_capability(node_name).tools == legacy_tools


def test_get_capability_raises_on_unknown_node_name():
    """A plan step naming a nonexistent agent is a bug to surface loudly, not
    degrade silently — relevant once a future planner can hallucinate names."""
    with pytest.raises(KeyError):
        get_capability("not_a_real_agent")


@pytest.mark.xfail(
    reason="SPEC-029 not yet implemented — laboratory/coordinator removal lands in SF059", strict=False
)
@pytest.mark.parametrize("node_name", ["laboratory", "coordinator"])
def test_get_capability_raises_on_a_removed_agent_name(node_name):
    """AC-029-02: `laboratory` and `coordinator` are removed capabilities,
    not renamed ones — looking them up must fail exactly like any other
    unknown name, never silently resolve to something else."""
    with pytest.raises(KeyError):
        get_capability(node_name)


@pytest.mark.parametrize("capability", [RADIOLOGY, DRUG_SAFETY, EVIDENCE])
def test_every_specialist_shares_the_clinician_voice(capability):
    """Single-agent mode makes whichever specialist gets routed the final
    answer verbatim (decision #24) — the product's voice must not change
    with the question. `radiology` was the one specialist missing this
    (found during the 2026-09-20 agent-reliability audit): it can still
    answer directly on a text-only misroute (intent_router.py's keyword
    rules match on question text, not on whether an image was provided)."""
    assert "Voice: write in plain, everyday language" in capability.role_prompt
