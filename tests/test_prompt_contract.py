"""Guards the coupling between agent role prompts and the test double's
script selection.

`tests/conftest.py::FakeLLMClient._script_for` picks the first script key that
is a *substring of the assembled system prompt*. Two keys are canonical across
the suite — "clinical evidence specialist" (EvidenceAgent) and
"coordinating physician-assistant" (ClinicalCoordinator).

If a role prompt is reworded, or the system-prompt assembly in
`MCPAgent.run()` changes shape, every workflow and API test silently falls
through to `default_script` and *still passes while asserting nothing*. That is
a silent failure, so it gets a loud test.

These assertions must stay green through the whole runtime migration; the role
prompt strings are moved byte-for-byte, never reflowed.
"""

from typing import Dict, List, Tuple

import pytest

from intelligence.agents import (
    ClinicalCoordinator,
    DrugSafetyAgent,
    EvidenceAgent,
    LabAgent,
    RadiologyAgent,
)
from tests.conftest import FakeLLMClient

# The two keys real test modules script against. Keep in sync with
# tests/test_workflow.py and tests/test_api_agents.py.
CANONICAL_SCRIPT_KEYS: Dict[str, str] = {
    "evidence": "clinical evidence specialist",
    "coordinator": "coordinating physician-assistant",
}

ALL_AGENTS = [
    RadiologyAgent,
    LabAgent,
    DrugSafetyAgent,
    EvidenceAgent,
    ClinicalCoordinator,
]


async def _assembled_system_prompt(agent_cls) -> str:
    """Run the agent against a fake client and return the system prompt it
    actually built — not a reconstruction, the real thing."""
    client = FakeLLMClient(default_script=[("answer", "ok")])
    await agent_cls(client).run("test query")
    assert client.chat_calls, f"{agent_cls.__name__} never called chat()"
    return client.chat_calls[0]["system_prompt"] or ""


@pytest.mark.parametrize(
    "agent_cls,key",
    [
        (EvidenceAgent, CANONICAL_SCRIPT_KEYS["evidence"]),
        (ClinicalCoordinator, CANONICAL_SCRIPT_KEYS["coordinator"]),
    ],
)
async def test_canonical_script_key_present_in_system_prompt(agent_cls, key):
    """The substring the suite scripts against survives prompt assembly."""
    prompt = await _assembled_system_prompt(agent_cls)
    assert key in prompt, (
        f"{agent_cls.__name__}'s assembled system prompt no longer contains "
        f"{key!r}. Every test scripting on this key has silently degraded to "
        f"FakeLLMClient.default_script."
    )


@pytest.mark.parametrize("agent_cls", ALL_AGENTS)
async def test_agent_role_prompt_is_non_empty(agent_cls):
    """An agent with an empty role_prompt is indistinguishable from any other
    agent to the script selector."""
    assert agent_cls.role_prompt.strip(), f"{agent_cls.__name__}.role_prompt is empty"


@pytest.mark.parametrize(
    "agent_cls,key",
    [
        (EvidenceAgent, CANONICAL_SCRIPT_KEYS["evidence"]),
        (ClinicalCoordinator, CANONICAL_SCRIPT_KEYS["coordinator"]),
    ],
)
async def test_script_selection_does_not_fall_through_to_default(agent_cls, key):
    """End-to-end check of the mechanism the other tests depend on: given a
    script keyed on the canonical substring, `_script_for` must resolve to that
    script rather than `default_script`."""
    target_script: List[Tuple] = [("answer", "scripted")]
    default_script: List[Tuple] = [("answer", "DEFAULT-FALLTHROUGH")]
    client = FakeLLMClient(scripts={key: target_script}, default_script=default_script)

    result = await agent_cls(client).run("test query")

    assert result.content == "scripted", (
        f"{agent_cls.__name__} fell through to default_script — the script key "
        f"{key!r} did not match its assembled system prompt."
    )


async def test_agent_names_are_distinct():
    """Agent identities double as dict keys in `agent_outputs` and as the
    `agent` field on the wire; a collision would silently drop an output."""
    names = [cls.name for cls in ALL_AGENTS]
    assert len(names) == len(set(names)), f"duplicate agent names: {names}"


async def test_role_prompts_are_mutually_distinguishable():
    """Script selection is substring-based and order-dependent. If one agent's
    role prompt were a substring of another's, `_script_for` could match the
    wrong script depending on dict ordering."""
    prompts = {cls.name: cls.role_prompt for cls in ALL_AGENTS}
    for name, prompt in prompts.items():
        for other_name, other_prompt in prompts.items():
            if name == other_name:
                continue
            assert prompt not in other_prompt, (
                f"{name}'s role_prompt is a substring of {other_name}'s — "
                "substring-based script selection would be ambiguous."
            )
