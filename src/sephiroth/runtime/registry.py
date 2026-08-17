"""The five clinical agents, as data.

Moved from `intelligence/agents/__init__.py`'s five hardcoded classes
(`docs/specs/SPEC-003-agent-runtime.md`). Role prompts are copied
**byte-for-byte** — including the canonical substrings
`"clinical evidence specialist"` and `"coordinating physician-assistant"` that
`tests/conftest.py::FakeLLMClient._script_for` matches against
(`docs/00-migration-charter.md`, the FakeLLMClient trap). Rewording any prompt
here is a separate, later change with its own test updates — not part of this
relocation.

`node_name` carries the underscore form used on the `routing` SSE event;
`id` carries the hyphenated display form used on `agent_completed` and in
`_persist`. Both existed implicitly before this phase (`drug_safety` vs
`drug-safety`); carrying them explicitly is what eventually lets the
frontend's `.replace("_", "-")` normalisation be removed.
"""

from __future__ import annotations

from sephiroth.contracts import AgentCapability

RADIOLOGY = AgentCapability(
    id="radiology",
    node_name="radiology",
    name="Radiology Agent",
    description="Analyzes medical images through the imaging + vision MCP servers.",
    role_prompt=(
        "You are the radiology specialist. When the patient context includes "
        "an image_path, FIRST call describe_medical_image to get an AI visual "
        "description, then reason over that description together with any "
        "structured analysis. Report findings with modality, location, and "
        "confidence. Clearly attribute what came from the vision model versus "
        "your clinical reasoning. Flag anything requiring urgent review."
    ),
    capabilities=["imaging_analysis", "vision"],
    tools=["inspect_medical_image", "analyze_medical_image", "describe_medical_image"],
    context_fields=["image_path", "conditions"],
)

LABORATORY = AgentCapability(
    id="laboratory",
    node_name="laboratory",
    name="Laboratory Agent",
    description="Interprets laboratory values present in the patient context.",
    role_prompt=(
        "You are the laboratory medicine specialist. Interpret the lab values "
        "in the patient context: flag values outside reference ranges, "
        "describe clinical significance, and note trends when prior values "
        "are available. Do not invent values that are not provided."
    ),
    capabilities=["lab_interpretation"],
    tools=[],  # works purely from the provided patient context
    context_fields=["lab_results", "conditions"],
)

DRUG_SAFETY = AgentCapability(
    id="drug-safety",
    node_name="drug_safety",
    name="Drug Safety Agent",
    description="Screens medication lists for interactions via the drug-safety server.",
    role_prompt=(
        "You are the medication safety specialist. Screen the patient's "
        "medication list for drug-drug interactions and summarize severity "
        "and recommended actions."
    ),
    capabilities=["medication_interaction", "drug_safety"],
    tools=["check_drug_interactions"],
    context_fields=["medications", "conditions"],
)

EVIDENCE = AgentCapability(
    id="evidence",
    node_name="evidence",
    name="Evidence Agent",
    description="Retrieves clinical guidelines and PubMed evidence — always cited.",
    role_prompt=(
        "You are the clinical evidence specialist. Ground every statement in "
        "retrieved guidelines or PubMed results. ALWAYS include the citation "
        "for each claim in the form [Source, Year] or [PMID:xxxx]. If no "
        "evidence is found, say so explicitly — never fabricate a citation."
    ),
    capabilities=["evidence_retrieval"],
    tools=["search_clinical_guidelines", "search_pubmed"],
    context_fields=["conditions"],
)

COORDINATOR = AgentCapability(
    id="coordinator",
    node_name="coordinator",
    name="Clinical Coordinator",
    description="Synthesizes the specialists' outputs into one clinical summary.",
    role_prompt=(
        "You are the coordinating physician-assistant. You receive analyses "
        "from specialist agents (radiology, laboratory, drug safety, "
        "evidence). Synthesize them into a single structured response with "
        "sections: Summary, Findings, Evidence (with citations), "
        "Recommendations. End with: 'This is decision support, not a "
        "diagnosis — professional review required.'"
    ),
    capabilities=["synthesis"],
    tools=["extract_medical_entities", "summarize_clinical_note"],
)

#: The four specialists a plan can select, keyed by node name — the exact set
#: `route_specialists` (planner.py) chooses from.
SPECIALISTS: dict[str, AgentCapability] = {
    "radiology": RADIOLOGY,
    "laboratory": LABORATORY,
    "drug_safety": DRUG_SAFETY,
    "evidence": EVIDENCE,
}

#: Every agent, including the coordinator, keyed by node name — the router's
#: lookup table.
AGENTS: dict[str, AgentCapability] = {**SPECIALISTS, "coordinator": COORDINATOR}


def get_capability(node_name: str) -> AgentCapability:
    """Resolve a node name to its capability record. Raises `KeyError` on an
    unknown name — a plan step naming a nonexistent agent is a bug to surface
    loudly, not degrade silently."""
    return AGENTS[node_name]


__all__ = [
    "AGENTS",
    "COORDINATOR",
    "DRUG_SAFETY",
    "EVIDENCE",
    "LABORATORY",
    "RADIOLOGY",
    "SPECIALISTS",
    "get_capability",
]
