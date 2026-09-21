"""Intent routing — pick exactly ONE specialist for a query.

Since `SPEC-029` (Phase 14) removed the multi-agent fan-out/coordinator
merge entirely, this is the only routing path in the executor — there is no
longer a separate "which specialists *could* contribute" planner to be
distinct from.

Three tiers, cheapest first — the same escalation shape used in the
Rocket Elevators orchestrator (`platform/orchestrator/router.py` there):

1. **Keyword rules** over the question text. Zero latency, deterministic,
   and covers the overwhelming majority of real clinical phrasing.
2. **Structured context signals** (`analyzer.analyze`) when the wording
   was ambiguous but the request carries an image path / medication list.
   Still zero latency.
3. **One `generate_json` classification call**, only for questions that
   neither tier resolved.

Every failure path degrades to `evidence` rather than raising: the
evidence specialist is the only one whose tools answer a general clinical
question with citations, so it is the correct default for "we could not
tell" — including a lab-value question, now that `laboratory` no longer
exists as a specialist (`ADR-016`): the deterministic curated rules in
`sephiroth.safety.risk` already surface that outside the chat path.

Rules are evaluated in order, first match wins, and are deliberately
narrow — a borderline question should fall through to a later tier rather
than be captured by an over-eager pattern.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sephiroth.clinical import GUIDELINE_CORE_TERMS

from .analyzer import analyze
from .registry import AGENTS

if TYPE_CHECKING:
    from sephiroth.models import ModelProvider

logger = logging.getLogger(__name__)

#: Fallback whenever intent cannot be determined — see module docstring.
DEFAULT_ROUTE = "evidence"

#: (node_name, pattern) evaluated in order; first match wins. Ordered by
#: intent, not topic. `evidence` is checked FIRST because guideline
#: phrasing ("what is the target for…", "first-line") states what the
#: clinician wants — a cited recommendation — regardless of which analyte
#: or drug the question happens to name. "What A1C goal is appropriate?"
#: is a guideline question that merely mentions a lab test; matching it on
#: the word "a1c" alone would answer the wrong question. The specialists
#: therefore match on *doing something to data in hand* (reading an image,
#: screening a regimen), not on domain vocabulary alone.
_FAST_RULES: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "evidence",
        re.compile(
            r"\b(" + "|".join(GUIDELINE_CORE_TERMS) + r"|standard of care|"
            r"evidence|indicated for|"
            r"(target|goal|threshold) (for|in|is|of)|"
            r"what (is|are) the (target|goal|recommended|first)|"
            r"what \w+ (goal|target)|"
            r"when (is|are|should|does)|"
            # Spanish: guía/recomendación phrasing, "qué hago si tengo X"
            # ("what do I do if I have X") is the canonical lay phrasing for
            # a symptom-management question and must land on `evidence`,
            # the only specialist whose tools answer a general clinical
            # question with citations — same default-to-evidence doctrine
            # as the English rules above.
            r"gu[ií]a\w*|primera l[íi]nea|recomendaci[óo]n\w*|recomendad\w*|"
            r"est[áa]ndar de (atenci[óo]n|cuidado)|"
            r"(objetivo|meta|umbral) (para|de|en)|"
            r"qu[ée] (hago|debo hacer|se recomienda) si|"
            r"cu[áa]l es el (objetivo|meta|tratamiento) (recomendado)?|"
            r"cu[áa]ndo (es|se|debo|debe))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "drug_safety",
        re.compile(
            r"\b(interact|interactions?|contraindicat\w*|safe together|"
            r"take together|combine (these|with)|drug[- ]drug|"
            # Spanish: interacciones/contraindicaciones
            r"interact[úu]an|interacci[óo]n\w*|contraindicad\w*|"
            r"tomar (juntos?|con)|combinar (estos?|con)|"
            r"seguro\w*.{0,20}juntos?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "radiology",
        re.compile(
            r"\b(x-?ray|radiograph\w*|imaging|mri|ct scan|ultrasound|"
            r"mammogram|scan (shows|of)|this (image|film|study)|"
            # Spanish: radiografía/resonancia/ecografía
            r"radiograf[íi]a|resonancia( magn[ée]tica)?|tomograf[íi]a|"
            r"ecograf[íi]a|imagen (muestra|de)|est[ae] (imagen|estudio))\b",
            re.IGNORECASE,
        ),
    ),
]

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {"agent": {"type": "string", "enum": list(AGENTS)}},
    "required": ["agent"],
}


def _classify_system_prompt() -> str:
    lines = [f"- {node}: {cap.description}" for node, cap in AGENTS.items()]
    return (
        "You are a clinical intake router. Read the clinician's question — "
        "in any language — and pick the ONE specialist best suited to "
        "answer it, regardless of what language it is written in. Available "
        "specialists:\n" + "\n".join(lines) + "\n"
        "Answer with exactly one specialist name. If the question is a "
        "general clinical question with no clear specialty, choose "
        f"'{DEFAULT_ROUTE}'."
    )


def _fast_classify(query: str) -> Optional[str]:
    """Keyword tier — a node name, or None when nothing matched."""
    for node, pattern in _FAST_RULES:
        if pattern.search(query):
            return node
    return None


def _from_context(context: Optional[Dict[str, Any]]) -> Optional[str]:
    """Structured-signal tier. Checked in the same precedence order as the
    keyword rules so an image-bearing request with a medication list still
    routes to drug safety only when the wording didn't already decide."""
    signals = analyze(context)
    if signals["has_image"]:
        return "radiology"
    if signals["has_medications"]:
        return "drug_safety"
    return None


async def _llm_classify(client: "ModelProvider", query: str) -> str:
    """LLM tier. Any failure — exception, non-dict payload, unknown agent
    name — degrades to `DEFAULT_ROUTE` rather than propagating: a routing
    miss should cost accuracy, never the whole consultation."""
    try:
        payload = await client.generate_json(
            prompt=f"Clinical question: {query.strip()}",
            schema=_CLASSIFY_SCHEMA,
            system_prompt=_classify_system_prompt(),
        )
    except Exception:
        logger.warning("intent_router: classification call failed, using %s", DEFAULT_ROUTE)
        return DEFAULT_ROUTE

    if not isinstance(payload, dict):
        return DEFAULT_ROUTE
    agent = payload.get("agent")
    if not isinstance(agent, str) or agent not in AGENTS:
        return DEFAULT_ROUTE
    return agent


async def route_intent(query: str, context: Optional[Dict[str, Any]], client: "ModelProvider") -> str:
    """Return the single specialist node name that should answer `query`."""
    if not query or not query.strip():
        return DEFAULT_ROUTE

    fast = _fast_classify(query)
    if fast is not None:
        logger.info("intent_router: keyword route=%s", fast)
        return fast

    from_context = _from_context(context)
    if from_context is not None:
        logger.info("intent_router: context route=%s", from_context)
        return from_context

    route = await _llm_classify(client, query)
    logger.info("intent_router: llm route=%s", route)
    return route


__all__ = ["DEFAULT_ROUTE", "route_intent"]
