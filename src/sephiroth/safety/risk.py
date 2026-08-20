"""
Risk engine — deterministic, rule-based safety flags for a patient.

Relocated verbatim from `intelligence/agents/risk_engine.py` (Phase 5,
`docs/00-migration-charter.md`'s shim schedule) — same philosophy as the
drug-safety server's curated table: a small, auditable rule set (no LLM
involved) evaluated at read-time, so flags are always current with the
stored labs/medications and nothing needs persisting or backfilling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from intelligence.mcp.drug_safety_server import find_interactions

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class LabRule:
    label: str
    severity: str  # "high" | "medium"
    detail: str

    def flag(self, value: float) -> Dict[str, str]:
        return {
            "source": "lab",
            "label": self.label,
            "severity": self.severity,
            "detail": self.detail.format(value=value),
        }


def _first_number(raw: Any) -> Optional[float]:
    match = _NUMBER_RE.search(str(raw))
    return float(match.group()) if match else None


# key in Patient.lab_results (lowercase) -> list of (predicate, rule)
LAB_RULES: Dict[str, List[tuple]] = {
    "potassium": [
        (lambda v: v < 3.5, LabRule("Hypokalemia", "high", "Potassium {value} mEq/L (< 3.5)")),
        (lambda v: v > 5.5, LabRule("Hyperkalemia", "high", "Potassium {value} mEq/L (> 5.5)")),
    ],
    "inr": [
        (lambda v: v > 3.5, LabRule("Supratherapeutic INR", "high", "INR {value} (> 3.5) — bleeding risk")),
    ],
    "hba1c": [
        (lambda v: v > 9, LabRule("Poor glycemic control", "medium", "HbA1c {value}% (> 9%)")),
    ],
    "bnp": [
        (
            lambda v: v > 400,
            LabRule("Elevated BNP", "medium", "BNP {value} pg/mL (> 400) — decompensation risk"),
        ),
    ],
    "ef": [
        (lambda v: v < 40, LabRule("Reduced ejection fraction", "high", "EF {value}% (< 40%)")),
    ],
    # Added for the Synthea-imported patient panel, which never carries
    # potassium/inr/bnp/ef — bmi/cholesterol/ldl are the only extra signal
    # it does provide, using standard ATP III / WHO cutoffs.
    "bmi": [
        (lambda v: 30 <= v < 40, LabRule("Obesity", "medium", "BMI {value} (≥ 30)")),
        (lambda v: v >= 40, LabRule("Severe obesity", "high", "BMI {value} (≥ 40)")),
    ],
    "cholesterol": [
        (lambda v: v >= 240, LabRule("High total cholesterol", "medium", "Cholesterol {value} mg/dL (≥ 240)")),
    ],
    "ldl": [
        (lambda v: 160 <= v < 190, LabRule("High LDL cholesterol", "medium", "LDL {value} mg/dL (≥ 160)")),
        (lambda v: v >= 190, LabRule("Very high LDL cholesterol", "high", "LDL {value} mg/dL (≥ 190)")),
    ],
}


def _blood_pressure_threshold_flags(systolic: float, diastolic: float) -> List[Dict[str, str]]:
    if systolic >= 160 or diastolic >= 100:
        return [
            {
                "source": "lab",
                "label": "Hypertensive range",
                "severity": "medium",
                "detail": f"BP {int(systolic)}/{int(diastolic)} (≥ 160/100)",
            }
        ]
    return []


def _blood_pressure_flags(raw: Any) -> List[Dict[str, str]]:
    """Parses a single combined "systolic/diastolic"-style value (the old
    demo-patient schema's `bp` key)."""
    numbers = [float(n) for n in _NUMBER_RE.findall(str(raw))]
    if len(numbers) < 2:
        return []
    return _blood_pressure_threshold_flags(numbers[0], numbers[1])


def assess_patient_risk(
    lab_results: Optional[Dict[str, Any]],
    medications: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """All rule-based risk flags for a patient (labs + drug interactions)."""
    flags: List[Dict[str, str]] = []
    by_key_lower = {key.strip().lower(): raw for key, raw in (lab_results or {}).items()}

    # Two BP schemas coexist: the old demo patients carry one combined "bp"
    # string ("140/90"); Synthea-imported patients carry two separate keys.
    if "bp" in by_key_lower:
        flags.extend(_blood_pressure_flags(by_key_lower["bp"]))
    elif "bp_systolic" in by_key_lower and "bp_diastolic" in by_key_lower:
        systolic = _first_number(by_key_lower["bp_systolic"])
        diastolic = _first_number(by_key_lower["bp_diastolic"])
        if systolic is not None and diastolic is not None:
            flags.extend(_blood_pressure_threshold_flags(systolic, diastolic))

    for key_lower, raw in by_key_lower.items():
        if key_lower in ("bp", "bp_systolic", "bp_diastolic"):
            continue
        rules = LAB_RULES.get(key_lower)
        if not rules:
            continue
        value = _first_number(raw)
        if value is None:
            continue
        for predicate, rule in rules:
            if predicate(value):
                flags.append(rule.flag(value))

    severity_map = {"major": "high", "moderate": "medium"}
    for interaction in find_interactions(medications or []):
        flags.append(
            {
                "source": "drug",
                "label": f"Interaction: {' + '.join(interaction['pair'])}",
                "severity": severity_map.get(interaction["severity"], "medium"),
                "detail": interaction["effect"],
            }
        )

    return flags


def lab_value_abnormality(test_name: str, value: float) -> tuple[bool, bool]:
    """Whether a single lab value would trigger a flag under the same
    `LAB_RULES` `assess_patient_risk` uses — shared so a persisted
    `LabResult.is_abnormal`/`is_critical` row never disagrees with the
    live risk flags computed from the same value."""
    rules = LAB_RULES.get(test_name.strip().lower())
    if not rules:
        return False, False
    triggered = [rule for predicate, rule in rules if predicate(value)]
    return bool(triggered), any(rule.severity == "high" for rule in triggered)


def bp_abnormality(systolic: float, diastolic: float) -> tuple[bool, bool]:
    """Same idea as `lab_value_abnormality`, for the two-key blood-pressure
    schema. Critical uses the standard hypertensive-crisis cutoff
    (180/110) — one tier above `_blood_pressure_threshold_flags`' single
    "Hypertensive range" severity, since that flag alone doesn't
    distinguish severity."""
    is_abnormal = bool(_blood_pressure_threshold_flags(systolic, diastolic))
    is_critical = systolic >= 180 or diastolic >= 110
    return is_abnormal, is_critical


def assess_risk_level(flags: List[Dict[str, str]]) -> str:
    """Overall level for a patient: high > medium > low (no flags)."""
    severities = {f["severity"] for f in flags}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


# Shared sort key for anywhere a patient list needs to surface the riskiest
# first (dashboard's critical-patients view, `/api/patients?sort=risk`) —
# one definition so both routers agree on tie-breaking (unknown levels sort
# last, after "low").
RISK_ORDER: Dict[str, int] = {"high": 0, "medium": 1, "low": 2}

__all__ = [
    "LabRule",
    "LAB_RULES",
    "RISK_ORDER",
    "assess_patient_risk",
    "assess_risk_level",
    "lab_value_abnormality",
    "bp_abnormality",
]
