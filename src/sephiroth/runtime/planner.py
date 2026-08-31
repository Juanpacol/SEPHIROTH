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
        "You are a clinical intake router. Read the clinician's question "
        "itself, not just the structured-data flags — a specialist can be "
        "relevant because the question asks about their domain (e.g. drug "
        "interactions, an imaging finding, a lab value) even if that data "
        "hasn't been entered into a structured field yet. Available "
        "agents:\n" + "\n".join(lines) + "\n"
        "Select only agents whose specialty is actually relevant to this "
        "question and context — do not select a specialist that has "
        "nothing to contribute."
    )


def _routing_prompt(context: Dict[str, Any] | None, query: str = "") -> str:
    signals = analyze(context)
    conditions = (context or {}).get("conditions") or []
    lines = [f"Clinical question: {query.strip()}" if query.strip() else "Clinical question: (none provided)"]
    if conditions:
        lines.append(f"Known conditions: {', '.join(str(c) for c in conditions)}")
    lines.append(f"has_image: {signals['has_image']}")
    lines.append(f"has_lab_results: {signals['has_lab_results']}")
    lines.append(f"has_medications: {signals['has_medications']}")
    return "\n".join(lines)


async def route_specialists_dynamic(
    context: Dict[str, Any] | None, client: "ModelProvider", query: str = ""
) -> List[str]:
    """LLM-driven capability matching (SPEC-008) — closes SPEC-003 NG-1.

    Reads the clinician's actual question (`query`) plus `conditions` from
    context, not just the three structured-data booleans — otherwise this
    routes almost as blindly as the static heuristic it's meant to improve
    on (e.g. "check for drug interactions with metformin" typed as free
    text, with no `medications` field populated, previously never reached
    `drug_safety`).

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
            prompt=_routing_prompt(context, query),
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
