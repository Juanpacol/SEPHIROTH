"""Static planning — `route_specialists`, moved verbatim.

This is the exact function `tests/test_workflow.py` imports and tests by name
(`docs/specs/SPEC-003-agent-runtime.md`) — not reimplemented, relocated. Same
name, same body, same four branches, so the parity gate (that test file,
unmodified) proves this relocation introduced no behavioral drift.

A dynamic, capability-matching planner is a later phase's addition, not a
change to this function.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .analyzer import analyze

SPECIALISTS = ("radiology", "laboratory", "drug_safety", "evidence")


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


__all__ = ["SPECIALISTS", "route_specialists"]
