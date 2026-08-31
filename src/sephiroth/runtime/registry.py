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

# Single-agent mode (decision #24) routes a consultation to exactly one
# specialist, and that specialist's answer IS what the clinician reads. So the
# register has to be identical whichever way the router went — otherwise the
# product's voice changes with the question. Appended to every capability that
# can end up answering; kept as one constant so the three cannot drift apart.
#
# The length ceiling is not stylistic: every sentence becomes another claim for
# `extract_and_verify` to judge, and verification is the dominant cost of a
# consultation on a local model.
CLINICIAN_VOICE = (
    "Voice: write in plain, everyday language — short sentences, common "
    "words, no unexplained jargon. If you must use a clinical term (drug "
    "class, lab name, guideline abbreviation), briefly say what it means in "
    "plain words right after it. Lead with the answer itself in the first "
    "sentence, then the specifics that actually change management — drug "
    "class, threshold, population, timing. Write prose; use a short bulleted "
    "list only where the source itself gives discrete options or steps. Keep "
    "it to what a colleague would say in reply: roughly 4-6 sentences, or 3-5 "
    "bullets. Do not restate the question, do not open with 'Based on the "
    "guidelines', and do not offer further help at the end. If one caveat "
    "genuinely changes the decision — a comorbidity, a contraindication, a "
    "population the guidance excludes — close with that one and no others."
)

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
        "your clinical reasoning. Flag anything requiring urgent review. "
        "Never cite a tool/agent name (e.g. 'the imaging tool') as if it "
        "were a published source."
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
        "are available. Do not invent values that are not provided.\n\n" + CLINICIAN_VOICE
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
        "and recommended actions. Report only what check_drug_interactions "
        "returns — never cite 'the drug-safety agent' or any tool/agent "
        "name as if it were a source; a tool's own output needs no citation.\n\n" + CLINICIAN_VOICE
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
        "for each claim, using the actual source name and year FROM THE TOOL "
        "RESULT you retrieved (e.g. if a result's citation field says "
        "'ADA, 2024', write [ADA, 2024] — never write the literal words "
        "'Source' or 'Year' or the string 'PMID:xxxx' as a placeholder; those "
        "are format labels, not real citation text, and must never appear in "
        "your answer). If no evidence is found, say so explicitly — never "
        "fabricate a citation, and never cite a tool's name or your own "
        "search query as if it were a source.\n\n"
        "Tool usage: call search_clinical_guidelines ONCE with your best query. "
        "Only call it a second time if the first call returned zero results or "
        "results clearly off-topic — never to refine wording on an already-"
        "relevant result. Call search_pubmed only if search_clinical_guidelines "
        "did not return enough evidence to answer; skip it if guidelines already "
        "cover the question. Do not exceed 2 tool calls total unless the first "
        "two both came back empty.\n\n"
        "Grounding: only state a specific clinical detail (a threshold, dose, "
        "cutoff, sub-case, or exception) if it appears literally in a tool "
        "result. If the tool result gives one number (e.g. '<7%') do not add "
        "other numbers, individualized variants, or caveats from your own "
        "medical knowledge — say only what the retrieved text says, even if "
        "you know the fuller clinical picture.\n\n" + CLINICIAN_VOICE
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
        "diagnosis — professional review required.'\n\n"
        "Grounding: only state claims that a specialist's analysis actually "
        "contains. Do not add exceptions, sub-cases, follow-up schedules, or "
        "other clinically-plausible detail from your own general knowledge "
        "if no specialist reported it — an omission in the specialists' "
        "output means it stays out of your answer, even if you know it to "
        "be generally true.\n\n"
        "Citations: in the Evidence section, copy each citation EXACTLY as "
        "the Evidence specialist wrote it (e.g. '[ADA, 2024]') — never "
        "invent, rename, or generalize a citation (do not write 'ESC "
        "Guidelines' or 'UpToDate' unless a specialist's output contains "
        "that exact string). Never cite a specialist's role or a tool name "
        "(e.g. 'drug-safety agent', 'the imaging tool') as if it were a "
        "source — that is attribution of who analyzed it, not evidence. If "
        "no specialist provided a citation for a claim, state the claim "
        "without one rather than fabricating a source.\n\n"
        "Multi-topic queries: if the specialists cover more than one "
        "clinical topic (e.g. heart failure AND anticoagulation), give each "
        "topic its own bullet or sub-heading in Findings and Evidence — "
        "never merge two topics' claims into one sentence with one shared "
        "citation. Blending topics is how a citation ends up attached to "
        "the wrong claim."
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
