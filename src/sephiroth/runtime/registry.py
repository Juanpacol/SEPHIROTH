"""The three clinical agents, as data.

Moved from `intelligence/agents/__init__.py`'s five hardcoded classes
(`docs/specs/SPEC-003-agent-runtime.md`). `laboratory` and `coordinator` were
removed in Phase 14 (`docs/specs/SPEC-029-agent-consolidation.md`,
`ADR-016`) — `laboratory` duplicated `sephiroth.safety.risk`'s deterministic
lab rules with no test on its own clinical output, and `coordinator`/the
multi-agent fan-out it merged had been unreachable in production since
`enable_single_agent_mode` defaulted `True`. Role prompts are copied
**byte-for-byte** from the pre-Phase-3 classes — including the canonical
substring `"clinical evidence specialist"` that
`tests/conftest.py::FakeLLMClient._script_for` matches against
(`docs/00-migration-charter.md`, the FakeLLMClient trap).

`node_name` carries the underscore form used on the `routing` SSE event;
`id` carries the hyphenated display form used on `agent_completed` and in
`_persist`. Both existed implicitly before Phase 3 (`drug_safety` vs
`drug-safety`); carrying them explicitly is what eventually lets the
frontend's `.replace("_", "-")` normalisation be removed.
"""

from __future__ import annotations

from sephiroth.contracts import AgentCapability

# `intent_router` routes a consultation to exactly one specialist, and that
# specialist's answer IS what the clinician reads (SPEC-029: this is now the
# only path, not a mode). So the register has to be identical whichever
# specialist gets picked — otherwise the product's voice changes with the
# question. Appended to every capability that can end up answering (all
# three — radiology included, since a text-only question can still misroute
# to it, per intent_router.py's keyword rules matching on question text
# regardless of whether an image was actually provided); kept as one
# constant so they cannot drift apart.
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
        "were a published source.\n\n" + CLINICIAN_VOICE
    ),
    capabilities=["imaging_analysis", "vision"],
    tools=["inspect_medical_image", "analyze_medical_image", "describe_medical_image"],
    context_fields=["image_path", "conditions"],
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
    require_tool_call=True,
    # `require_tool_call=True` above forces tool_choice on round 0, but the
    # 2026-09-20 audit found the omission still slips past that on a local
    # model that ignores tool_choice outright (`ToolCallOmittedError`,
    # agent.py).
    #
    # `model_hint="llama3-groq-tool-use:8b"` was tried here as a targeted
    # fix (SF056) on the theory that a model fine-tuned + DPO'd specifically
    # for tool-calling (89.06% BFCL) would honor `require_tool_call` more
    # reliably than the generalist `qwen3:8b` every other agent uses.
    # Reverted the same day, confirmed by direct A/B against Ollama's
    # `/api/chat` with EVIDENCE's real ~400-word system prompt + both real
    # tool schemas: `llama3-groq-tool-use:8b` fabricated an answer with an
    # invented citation (never called the tool) on the exact query that
    # motivated `require_tool_call` in the first place, while `qwen3:8b`
    # called the tool correctly on the identical input. The benchmark score
    # is for short, tool-focused prompts; this model's fine-tuning appears
    # to lose the tool-calling habit against a long, multi-rule clinical
    # system prompt — the opposite of what EVIDENCE actually needs. No
    # `model_hint` set: falls back to whatever `get_llm_client()` returns
    # by default (`qwen3:8b` locally), same as every other specialist.
)

#: The three specialists `intent_router` selects from, keyed by node name —
#: since SPEC-029 there is no separate "specialists vs. all agents" set.
AGENTS: dict[str, AgentCapability] = {
    "radiology": RADIOLOGY,
    "drug_safety": DRUG_SAFETY,
    "evidence": EVIDENCE,
}


def get_capability(node_name: str) -> AgentCapability:
    """Resolve a node name to its capability record. Raises `KeyError` on an
    unknown name — a plan step naming a nonexistent agent is a bug to surface
    loudly, not degrade silently."""
    return AGENTS[node_name]


__all__ = [
    "AGENTS",
    "DRUG_SAFETY",
    "EVIDENCE",
    "RADIOLOGY",
    "get_capability",
]
