"""
Explainability — a human-readable reasoning trace for each consultation.

Deliberately deterministic and template-based (no extra LLM call): the whole
point is trustworthiness, so this layer must not add another hallucination
surface. It is derived on demand from data the workflow already records
(agents involved, tagged tool calls, citation report) — nothing is persisted.
"""

from __future__ import annotations

from typing import Any, Dict, List

# tool name -> template; {placeholders} are filled from the call's arguments.
_ACTION_TEMPLATES: Dict[str, str] = {
    "search_clinical_guidelines": "Searched clinical guidelines for “{query}”",
    "search_pubmed": "Searched PubMed for “{query}”",
    "check_drug_interactions": "Screened {medications} for drug-drug interactions",
    "extract_medical_entities": "Extracted medical entities from the clinical text",
    "summarize_clinical_note": "Summarized the clinical note",
    "inspect_medical_image": "Inspected image metadata ({image_path})",
    "analyze_medical_image": "Ran structured image analysis ({modality})",
    "describe_medical_image": "Generated an AI visual description of the image",
}

# Agents that contribute without calling tools still deserve a step.
_NO_TOOL_ACTIONS: Dict[str, str] = {
    "laboratory": "Interpreted the lab values in the patient context",
    "coordinator": "Synthesized the specialist analyses into the final answer",
}


def _describe_call(call: Dict[str, Any]) -> str:
    name = call.get("name", "unknown_tool")
    template = _ACTION_TEMPLATES.get(name)
    if template is None:
        return f"Called {name}"
    arguments = call.get("arguments") or {}
    safe = {
        "query": str(arguments.get("query", ""))[:80],
        "medications": ", ".join(map(str, arguments.get("medications", []))) or "the medication list",
        "image_path": str(arguments.get("image_path", "the image")),
        "modality": str(arguments.get("modality", "unspecified modality")),
    }
    try:
        return template.format(**safe)
    except (KeyError, IndexError):
        return f"Called {name}"


def build_explanation(
    agents: List[str],
    tool_calls: List[Dict[str, Any]],
    citation_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the reasoning trace shown in the UI's explainability panel."""
    steps: List[Dict[str, str]] = []
    agents_with_calls = set()

    for call in tool_calls or []:
        agent = call.get("agent", "unknown")
        agents_with_calls.add(agent)
        steps.append({"agent": agent, "action": _describe_call(call), "tool": call.get("name", "")})

    # One generic step for agents that ran but never reached for a tool.
    for agent in agents or []:
        if agent not in agents_with_calls:
            steps.append(
                {
                    "agent": agent,
                    "action": _NO_TOOL_ACTIONS.get(
                        agent, "Analyzed the patient context directly"
                    ),
                    "tool": "",
                }
            )

    report = citation_report or {}
    return {
        "steps": steps,
        "citations_verified": len(report.get("verified", [])),
        "citations_removed": len(report.get("fabricated", [])),
    }
