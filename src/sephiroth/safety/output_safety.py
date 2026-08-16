"""Minimal input-facing safety check (F-041) — scope deliberately narrow.

Only two things are in scope this phase:
1. A prompt-injection heuristic on the *input* query.
2. Wiring a match into `abstention.decide` as `POLICY_RESTRICTION`.

Explicitly deferred: PHI redaction of clinical text (the product exists to
show a clinician their own patient's clinical content back to them —
redacting it would break the product; this is the same trade-off already
documented in CLAUDE.md's privacy notice), output-side toxicity/jailbreak
classifiers, and rate limiting. These are separate, larger topics better
served by their own future spec once real telemetry shows they're needed.
"""

from __future__ import annotations

import re
from typing import List

from sephiroth.contracts import RiskLevel, SafetyFlag

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all|any|the)?\s*(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"disregard\s+(your|all)\s*(system\s*prompt|instructions|rules)", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s*(system\s*prompt|instructions)", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(if\s+you\s+were|a)\b", re.IGNORECASE),
]


def check_input(query: str) -> List[SafetyFlag]:
    """A single `prompt_injection` flag if any heuristic pattern matches;
    `[]` otherwise. Deliberately a flat pass, not a scored classifier — cheap
    and auditable, matched against the same standard of "simplest that
    satisfies the spec" used throughout this migration."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query or ""):
            return [
                SafetyFlag(
                    code="prompt_injection",
                    severity=RiskLevel.HIGH,
                    message="Input matched a prompt-injection heuristic pattern.",
                )
            ]
    return []


__all__ = ["check_input"]
