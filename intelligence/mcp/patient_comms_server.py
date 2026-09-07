"""FastMCP server exposing patient-message drafting. Deliberately the
only capability here: this tool drafts prose for an *already-decided*
follow-up -- it never decides whether or when to contact a patient
(that is deterministic workflow logic, `platform/api/workflows/`) and
its output never reaches a patient without a clinician approving it
through `POST /api/approvals/{id}/approve` (SPEC-013). No `patient_id`
parameter and no DB handle -- it cannot widen PHI scope beyond the
facts it's explicitly given.
"""

from typing import Any, Dict

from fastmcp import FastMCP

from sephiroth.models import LLMUnavailableError, get_llm_client

mcp = FastMCP(
    name="patient-comms",
    instructions="Drafts short, plain-language patient-facing messages for already-decided follow-ups.",
)

_SYSTEM_PROMPT = (
    "You draft short, warm, plain-language messages FROM a clinic TO a "
    "patient about a follow-up that a clinician has already decided on. "
    "You do not decide whether to contact the patient, what treatment to "
    "give, or make any new clinical recommendation -- only phrase the "
    "given facts clearly. Never invent facts not provided. Keep it under "
    "80 words. No diagnosis, no dosing changes, no medical advice beyond "
    "what's given. A clinician will review before anything is sent."
)


def _build_prompt(
    purpose: str, patient_first_name: str, facts: Dict[str, Any], language: str, reading_level: str
) -> str:
    fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items()) or "(no additional facts given)"
    return (
        f"Purpose: {purpose}\n"
        f"Patient's first name: {patient_first_name}\n"
        f"Language: {language}\n"
        f"Reading level: {reading_level}\n"
        f"Facts:\n{fact_lines}\n\n"
        "Draft the message now."
    )


async def draft_message(
    purpose: str,
    patient_first_name: str,
    facts: Dict[str, Any],
    language: str = "en",
    reading_level: str = "plain",
) -> str:
    """Plain function shared by the `@mcp.tool` below and
    `platform/api/routers/approvals.py`'s on-demand draft endpoint --
    same split as `find_interactions`/`check_drug_interactions`
    (`drug_safety_server.py`). Never called from the tick (SPEC-009's
    "no LLM inside the tick, ever") -- only on-demand, when a clinician
    opens the approval queue."""
    client = get_llm_client()
    prompt = _build_prompt(purpose, patient_first_name, facts, language, reading_level)
    result = await client.chat(messages=[{"role": "user", "content": prompt}], system_prompt=_SYSTEM_PROMPT)
    return result.content.strip()


@mcp.tool
async def draft_patient_message(
    purpose: str,
    patient_first_name: str,
    facts: Dict[str, Any],
    language: str = "en",
    reading_level: str = "plain",
) -> Dict[str, Any]:
    """Draft a short, plain-language message to a patient about an
    already-decided follow-up. Never decides *whether* to contact
    anyone -- that decision has already been made. Always requires
    clinician approval before the patient sees it."""
    try:
        draft = await draft_message(purpose, patient_first_name, facts, language, reading_level)
    except LLMUnavailableError as exc:
        return {
            "draft": "",
            "purpose": purpose,
            "language": language,
            "requires_clinician_approval": True,
            "error": str(exc),
            "disclaimer": "Draft generation is unavailable right now -- retry, or write the message by hand.",
        }

    return {
        "draft": draft,
        "purpose": purpose,
        "language": language,
        "facts_used": facts,
        "requires_clinician_approval": True,
        "disclaimer": ("AI-drafted text. Not sent to the patient until a clinician reviews and approves it."),
    }


__all__ = ["mcp", "draft_message", "draft_patient_message"]
