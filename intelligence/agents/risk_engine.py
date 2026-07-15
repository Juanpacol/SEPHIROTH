"""
Risk engine — deterministic, rule-based safety flags for a patient.

Same philosophy as the drug-safety server's curated table: a small,
auditable rule set (no LLM involved) evaluated at read-time, so flags are
always current with the stored labs/medications and nothing needs
persisting or backfilling.
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
}


def _blood_pressure_flags(raw: Any) -> List[Dict[str, str]]:
    numbers = [float(n) for n in _NUMBER_RE.findall(str(raw))]
    if len(numbers) < 2:
        return []
    systolic, diastolic = numbers[0], numbers[1]
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


def assess_patient_risk(
    lab_results: Optional[Dict[str, Any]],
    medications: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """All rule-based risk flags for a patient (labs + drug interactions)."""
    flags: List[Dict[str, str]] = []

    for key, raw in (lab_results or {}).items():
        key_lower = key.strip().lower()
        if key_lower == "bp":
            flags.extend(_blood_pressure_flags(raw))
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


def assess_risk_level(flags: List[Dict[str, str]]) -> str:
    """Overall level for a patient: high > medium > low (no flags)."""
    severities = {f["severity"] for f in flags}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"
