"""The five `AgentCapability` records match the pre-Phase-3 hardcoded classes
exactly — same identity, same tools, same node/display name split.

Verifies AC-003-04 (`docs/specs/SPEC-003-agent-runtime.md`).
"""

import pytest

from sephiroth.runtime.registry import (
    AGENTS,
    COORDINATOR,
    DRUG_SAFETY,
    EVIDENCE,
    LABORATORY,
    RADIOLOGY,
    SPECIALISTS,
    get_capability,
)

pytestmark = pytest.mark.spec

# The exact `allowed_tools` lists from the pre-Phase-3 hardcoded classes
# (intelligence/agents/__init__.py, before this phase), keyed by node name.
LEGACY_ALLOWED_TOOLS = {
    "radiology": ["inspect_medical_image", "analyze_medical_image", "describe_medical_image"],
    "laboratory": [],  # was `None` — both mean "no tools"
    "drug_safety": ["check_drug_interactions"],
    "evidence": ["search_clinical_guidelines", "search_pubmed"],
    "coordinator": ["extract_medical_entities", "summarize_clinical_note"],
}


def test_specialists_are_the_four_the_planner_selects_from():
    assert set(SPECIALISTS) == {"radiology", "laboratory", "drug_safety", "evidence"}


def test_agents_includes_the_coordinator_too():
    assert set(AGENTS) == {"radiology", "laboratory", "drug_safety", "evidence", "coordinator"}


@pytest.mark.parametrize(
    "capability,expected_id,expected_node_name",
    [
        (RADIOLOGY, "radiology", "radiology"),
        (LABORATORY, "laboratory", "laboratory"),
        (DRUG_SAFETY, "drug-safety", "drug_safety"),
        (EVIDENCE, "evidence", "evidence"),
        (COORDINATOR, "coordinator", "coordinator"),
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
