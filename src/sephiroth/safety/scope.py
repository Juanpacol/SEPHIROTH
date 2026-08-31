"""Clinical-scope guard — rejects questions that are not clinical at all.

Mirrors `output_safety.check_input` exactly: a flat, deterministic regex
pass, not a scored classifier — cheap, auditable, and consistent with the
rest of this module.

Before this existed, an off-topic question (taxes, legal advice, a recipe)
only ever "worked" by accident: `search_clinical_guidelines` returned zero
results, so `INSUFFICIENT_EVIDENCE` abstention fired downstream after a full
consultation had already run. Expanding the corpus (`data/rag/corpus_
primary_care.py`) widens the vocabulary that corpus can match on, which
weakens that accident — a corpus with ~60 common-complaint documents is more
likely to spuriously match a few keywords in an unrelated question than a
37-document specialist corpus was. This guard makes the rejection explicit
and moves it before any tool call or model turn runs (see
`runtime/executor.py::run_consultation`), instead of relying on retrieval
coming up empty.

Deliberately a **blocklist of clearly non-clinical domains**, not a
whitelist of "sounds medical" — a whitelist would false-positive on
legitimate lay-language symptom questions like "qué hago si tengo dolor de
cabeza", which is exactly the phrasing this project exists to answer.
"""

from __future__ import annotations

import re
from typing import List

from sephiroth.contracts import RiskLevel, SafetyFlag

_OUT_OF_SCOPE_PATTERNS = [
    # Tax / finance / accounting
    re.compile(
        r"\b(tax (returns?|filing|deductions?)|quarterly tax|file (my|your) taxes|"
        r"stock (market|portfolio)|cryptocurrency|401\(?k\)?|"
        r"declaraci[óo]n de (impuestos|renta)|impuestos trimestrales|"
        r"bolsa de valores|criptomoneda)\b",
        re.IGNORECASE,
    ),
    # Legal advice
    re.compile(
        r"\b(legal advice|file a lawsuit|divorce (proceedings|paperwork)|"
        r"draft a contract|asesor[íi]a legal|demandar a|"
        r"papeles de divorcio|redactar un contrato)\b",
        re.IGNORECASE,
    ),
    # Software / programming
    re.compile(
        r"\b(write (a|some) (code|python|javascript|sql)|debug (this|my) "
        r"(code|script)|programming language|source code|"
        r"escrib\w* (un|c[óo]digo)|depurar (mi|este) c[óo]digo)\b",
        re.IGNORECASE,
    ),
    # Cooking / recipes
    re.compile(
        r"\b(recipe for|how to (cook|bake)|cooking instructions|"
        r"receta (para|de)|c[óo]mo (cocinar|hornear))\b",
        re.IGNORECASE,
    ),
]


def check_scope(query: str) -> List[SafetyFlag]:
    """A single `out_of_scope` flag if the query matches a clearly
    non-clinical domain pattern; `[]` otherwise (including for anything
    ambiguous — this only catches unambiguous off-topic requests, never a
    borderline clinical one)."""
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(query or ""):
            return [
                SafetyFlag(
                    code="out_of_scope",
                    severity=RiskLevel.LOW,
                    message="Input matched a non-clinical domain pattern (not a medical question).",
                )
            ]
    return []


__all__ = ["check_scope"]
