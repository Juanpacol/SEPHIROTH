"""Shim — relocated to `src/sephiroth/safety/risk.py` (Phase 5).

Per `docs/00-migration-charter.md`'s shim rules: re-exports only, no logic.
Deleted the phase after this one, unless it becomes permanent.
"""

from sephiroth.safety.risk import LAB_RULES, LabRule, assess_patient_risk, assess_risk_level

__all__ = ["LabRule", "LAB_RULES", "assess_patient_risk", "assess_risk_level"]
