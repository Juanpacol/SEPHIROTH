"""Resolve node names to capability records.

In this phase the planner already emits exactly the right node names in the
right order, so this is a direct lookup — a capability-matching router (asking
"who can do X?" instead of naming a node) is a later phase's addition, not a
redesign of this one. Kept as its own module regardless of today's
simplicity, since that future router replaces only this file.
"""

from __future__ import annotations

from typing import List

from sephiroth.contracts import AgentCapability

from .registry import get_capability


def resolve(node_names: List[str]) -> List[AgentCapability]:
    """Resolve an ordered list of node names to their capability records,
    preserving order — order is observable on the wire (merge order in
    `agents_involved`/`final.tool_calls`)."""
    return [get_capability(name) for name in node_names]


__all__ = ["resolve"]
