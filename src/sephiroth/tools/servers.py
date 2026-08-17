"""Server registration and capability tags.

`SERVERS` is the exact set already assembled in
`intelligence/mcp/registry.py` before this phase — moved, not changed.
`TOOL_CAPABILITIES` is new: a hand-authored map from tool name to capability
tags, consumed by `ToolRuntime.tags_for()`. Deliberately a literal dict, not a
YAML loader — that level of generality belongs to the Phase 3 agent registry
(`docs/02-agents/registry.md`), not here.
"""

from __future__ import annotations

from intelligence.mcp import drug_safety_server, imaging_server, nlp_server, rag_server, vision_server

SERVERS = [
    nlp_server.mcp,
    imaging_server.mcp,
    rag_server.mcp,
    drug_safety_server.mcp,
    vision_server.mcp,
]

#: Every key must be a real tool name discoverable via `ToolRuntime.load()`.
TOOL_CAPABILITIES: dict[str, list[str]] = {
    "check_drug_interactions": ["medication_interaction", "drug_safety"],
    "inspect_medical_image": ["imaging_metadata"],
    "analyze_medical_image": ["imaging_analysis"],
    "describe_medical_image": ["imaging_analysis", "vision"],
    "extract_medical_entities": ["clinical_nlp"],
    "summarize_clinical_note": ["clinical_nlp"],
    "search_clinical_guidelines": ["evidence_retrieval"],
    "search_pubmed": ["evidence_retrieval"],
}

__all__ = ["SERVERS", "TOOL_CAPABILITIES"]
