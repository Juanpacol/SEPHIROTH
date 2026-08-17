"""Static planning — `route_specialists`, moved verbatim.

This is the exact function `tests/test_workflow.py` imports and tests by name
(`docs/specs/SPEC-003-agent-runtime.md`) — not reimplemented, relocated. Same
name, same body, same four branches, so the parity gate (that test file,
unmodified) proves this relocation introduced no behavioral drift.

`route_specialists_dynamic` (SPEC-008, closes SPEC-003 NG-1) is an
additive sibling, not a replacement: it degrades to `route_specialists`
on any model failure or invalid payload, and is only reached at all when
`settings.enable_dynamic_planner` is on (default off, so the static path
above stays the only one the offline eval — `--mode ci`, no live model —
ever exercises).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from .analyzer import analyze
from .registry import SPECIALISTS as CAPABILITY_REGISTRY

if TYPE_CHECKING:
    from sephiroth.models import ModelProvider

SPECIALISTS = ("radiology", "laboratory", "drug_safety", "evidence")

_ROUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "agents": {
            "type": "array",
            "items": {"type": "string", "enum": list(SPECIALISTS)},
        }
    },
    "required": ["agents"],
}


def route_specialists(context: Dict[str, Any] | None) -> List[str]:
    """Which specialist branches to run, based on available inputs."""
    signals = analyze(context)
    branches = ["evidence"]  # evidence retrieval always runs
    if signals["has_image"]:
        branches.append("radiology")
    if signals["has_lab_results"]:
        branches.append("laboratory")
    if signals["has_medications"]:
        branches.append("drug_safety")
    return branches


def _routing_system_prompt() -> str:
    lines = [f"- {node}: {cap.description}" for node, cap in CAPABILITY_REGISTRY.items()]
    return (
        "You are a clinical intake router. Given the patient context signals "
        "below, decide which specialist agents should analyze this case. "
        "Available agents:\n" + "\n".join(lines) + "\n"
        "Select only agents whose specialty is relevant to the provided "
        "context — do not select a specialist for data that is not present."
    )


def _routing_prompt(context: Dict[str, Any] | None) -> str:
    signals = analyze(context)
    return (
        f"has_image: {signals['has_image']}\n"
        f"has_lab_results: {signals['has_lab_results']}\n"
        f"has_medications: {signals['has_medications']}"
    )


async def route_specialists_dynamic(context: Dict[str, Any] | None, client: "ModelProvider") -> List[str]:
    """LLM-driven capability matching (SPEC-008) — closes SPEC-003 NG-1.

    Degrades to `route_specialists` (the static heuristic) on any
    `generate_json` exception, a non-dict payload, a missing/empty/invalid
    `agents` list, or once every listed agent is filtered out as unknown —
    the static planner is always available and never itself fails, so
    there is no case where routing produces zero specialists because of
    this function.
    """
    fallback = route_specialists(context)
    try:
        payload = await client.generate_json(
            prompt=_routing_prompt(context),
            schema=_ROUTING_SCHEMA,
            system_prompt=_routing_system_prompt(),
        )
    except Exception:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        return fallback
    valid = [a for a in dict.fromkeys(agents) if isinstance(a, str) and a in SPECIALISTS]
    return valid or fallback


__all__ = ["SPECIALISTS", "route_specialists", "route_specialists_dynamic"]
