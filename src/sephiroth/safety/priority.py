"""
Clinical Priority Score — a numeric proxy over the existing rule-based
risk level (`sephiroth.safety.risk.assess_risk_level`), not a new composite
formula. Computed at read-time, same philosophy as `risk.py` (decision #10):
nothing here is persisted or backfilled.
"""

from __future__ import annotations

from typing import Dict

PRIORITY_SCORE: Dict[str, int] = {"high": 3, "medium": 2, "low": 1}


def compute_priority_score(risk_level: str) -> int:
    """Maps a risk level to a numeric priority score (0-3, higher = more urgent)."""
    return PRIORITY_SCORE.get(risk_level, 0)


__all__ = ["PRIORITY_SCORE", "compute_priority_score"]
