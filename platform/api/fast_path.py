"""Fast-path lookups — bypass the multi-agent LLM pipeline entirely for
query shapes that are pure data retrieval, not synthesis.

**Why this is safe, not just fast.** The full pipeline (specialist →
coordinator → citation guard → claim verification → abstention) exists
because free-text LLM synthesis can fabricate. A fast-path answer never
synthesizes anything — it returns a tool's own structured result
(`search_clinical_guidelines`, `check_drug_interactions`) verbatim, with
the tool's own citation attached unchanged. There is nothing for an LLM
to hallucinate because no LLM generates the answer text; Citation Guard
and claim verification would have nothing to check that isn't already
guaranteed true by construction. This is a stronger safety position than
"skip verification for low-stakes questions" — it isn't skipped, it's
structurally unnecessary.

**Why this is a rules-based router, not an LLM router.** An LLM call to
classify intent would reintroduce the exact latency this exists to avoid
(one more sequential round-trip). Keyword/regex matching is instant and
deterministic — a false negative just falls through to the full pipeline
(never wrong, only slower); a false positive is caught by the pattern's
own precondition checks (e.g. drug-interaction fast path requires an
actual medication list to be resolvable).

Two triggers today:
1. Drug interaction questions — resolvable whenever medications are known
   (from `context["medications"]` or the patient's chart), since this is
   never patient-context-free the way a guideline lookup can be.
2. Guideline/evidence lookups — restricted to `patient_id`-less queries.
   A patient-specific question ("is THIS patient's regimen appropriate")
   needs synthesis across their actual data and stays on the full path;
   `tests/test_runtime_executor.py::test_run_consultation_abstains_on_unsupported_high_risk_claim`
   is exactly why this router must never try to be clever about routing
   patient-specific questions here — see that test before loosening this.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from data.schemas import Patient
from intelligence.mcp.drug_safety_server import INTERACTIONS
from intelligence.mcp.rag_server import MAX_GUIDELINE_RESULTS
from sephiroth.tools import get_tool_runtime

#: Every drug name the curated interaction table knows about, lowercase —
#: lets a plain-language question ("do warfarin and ibuprofen interact?")
#: resolve its own medication list without a patient chart or explicit
#: context, by naming the drugs directly in the question.
_KNOWN_DRUG_NAMES = frozenset(name for pair in INTERACTIONS for name in pair)


def _extract_named_medications(query: str) -> List[str]:
    text = query.lower()
    return [name for name in _KNOWN_DRUG_NAMES if re.search(rf"\b{re.escape(name)}\b", text)]


_DRUG_INTERACTION_RE = re.compile(
    r"\b(interact|interaction|combine|combination|safe together|contraindicat)", re.I
)

# Deliberately excludes "this patient"/"my patient"/possessive phrasing —
# those signal a question that needs THIS patient's actual data synthesized,
# not a general guideline lookup. Keep in sync with the module docstring's
# safety argument: this router must stay conservative about what it claims.
_GUIDELINE_RE = re.compile(
    r"\b(guideline|first-line|first line|recommend|target|threshold|"
    r"when (is|should)|what is the (target|recommended))\b",
    re.I,
)
_PATIENT_SPECIFIC_RE = re.compile(r"\b(this patient|my patient|patient'?s|their regimen)\b", re.I)


async def _resolve_medications(
    query: str, patient_id: str, context: Dict[str, Any], session: AsyncSession
) -> List[str]:
    from_context = context.get("medications")
    if isinstance(from_context, list) and from_context:
        return from_context
    if patient_id:
        patient = await session.get(Patient, patient_id)
        if patient:
            return patient.medications
    return _extract_named_medications(query)


def _format_rag_answer(results: List[Dict[str, Any]]) -> Optional[tuple[str, List[str]]]:
    """Verbatim excerpt + its real citation — never paraphrased. Only the
    single best match: at these corpus sizes and query lengths, retrieval
    scores are low and close together, so a second "top" result is often
    only tangentially related (e.g. a UTI guideline surfacing alongside a
    hypertension one on shared wording like "first-line"). One precise
    excerpt beats two where one is noise.

    Returns `None` — never a fabricated citation — if the top hit has no
    real citation or source text. Every `Document` in the seed corpus
    always has one (`Document.citation` falls back to the required
    `source` field), so this is a defensive bail-out for malformed data,
    not a path exercised in practice; the old code substituted the literal
    string "uncited" here, which could land in `citation_report["verified"]`
    marking a nonexistent citation as verified."""
    top = results[0]
    citation = top.get("citation") or top.get("source")
    if not citation:
        return None
    return f"{top['content']}\n\n[{citation}]", [citation]


def _format_drug_answer(payload: Dict[str, Any]) -> str:
    if payload.get("interactions_found", 0) == 0:
        checked = ", ".join(payload.get("medications_checked", []))
        return f"No known interactions found among: {checked}."
    lines = [f"{payload['interactions_found']} interaction(s) found:"]
    for i in payload.get("interactions", []):
        pair = " + ".join(i["pair"])
        lines.append(f"- **{pair}** ({i['severity']}): {i['effect']} {i['recommendation']}")
    return "\n".join(lines)


async def try_fast_path(
    query: str, patient_id: str, context: Dict[str, Any], session: AsyncSession
) -> Optional[Dict[str, Any]]:
    """Returns a final-state-shaped dict (same keys `_persist` expects) if
    a fast path applies, else None — caller falls through to the full
    multi-agent pipeline unchanged."""
    registry = get_tool_runtime()
    await registry.load()

    if _DRUG_INTERACTION_RE.search(query):
        medications = await _resolve_medications(query, patient_id, context, session)
        if len(medications) >= 2:
            result = await registry.execute("check_drug_interactions", {"medications": medications})
            answer = _format_drug_answer(result)
            return {
                "source": "drug-safety",
                "final_answer": answer,
                "tool_calls": [
                    {
                        "name": "check_drug_interactions",
                        "arguments": {"medications": medications},
                        "result": result,
                    }
                ],
                "citation_report": {"verified": [], "fabricated": []},
            }

    if not patient_id and not _PATIENT_SPECIFIC_RE.search(query) and _GUIDELINE_RE.search(query):
        # Request exactly what the tool honors — it caps at
        # MAX_GUIDELINE_RESULTS regardless of what's asked (see
        # intelligence/mcp/rag_server.py), so asking for more here was a
        # silent no-op.
        result = await registry.execute(
            "search_clinical_guidelines", {"query": query, "top_k": MAX_GUIDELINE_RESULTS}
        )
        results = result.get("results", [])
        # A weak top hit — e.g. a single coincidentally shared keyword with
        # no real embedding-corroborated match — must never become the
        # final answer unchecked: this path skips citation guard and claim
        # verification entirely (see the module docstring's safety
        # argument), so it can only stand in for the full pipeline when the
        # match is actually strong. Below the floor, fall through instead.
        if results and results[0].get("score", 0.0) >= settings.fast_path_min_score:
            formatted = _format_rag_answer(results)
            if formatted is not None:
                answer, citations = formatted
                return {
                    "source": "evidence",
                    "final_answer": answer,
                    "tool_calls": [
                        {
                            "name": "search_clinical_guidelines",
                            "arguments": {"query": query},
                            "result": result,
                        }
                    ],
                    "citation_report": {"verified": citations, "fabricated": []},
                }

    return None


__all__ = ["try_fast_path"]
