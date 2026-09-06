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
#: Dose ("500mg", "10 mL") and form ("tablet", "oral") noise, stripped before
#: two medication strings are compared.
_DOSE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|units?|%)\b", re.IGNORECASE)
_FORM_RE = re.compile(
    r"\b(?:tablet|tablets|capsule|capsules|oral|solution|injection|inj|susp|suspension|cream|"
    r"ointment|patch|inhaler|drops?|daily|bid|tid|qid|prn)\b",
    re.IGNORECASE,
)


@dataclass
class LabRule:
    #: Stable identity for this rule, independent of what it is called on
    #: screen (SPEC-021). Deduplication keys on this rather than on `label`,
    #: because a label is display copy: rewording "Hypokalemia" to "Low
    #: potassium" would otherwise silently duplicate every open alert.
    key: str
    label: str
    severity: str  # "high" | "medium"
    detail: str
    #: Where the threshold comes from. Every warning has to be able to say
    #: why it fired -- a rule a clinician cannot audit is one they have to
    #: take on faith.
    source: str = ""

    def flag(self, value: float) -> Dict[str, str]:
        return {
            "source": "lab",
            "rule_key": self.key,
            "label": self.label,
            "severity": self.severity,
            "detail": self.detail.format(value=value),
            "rule_source": self.source,
            "kind": "clinical",
        }


def _first_number(raw: Any) -> Optional[float]:
    match = _NUMBER_RE.search(str(raw))
    return float(match.group()) if match else None


# key in Patient.lab_results (lowercase) -> list of (predicate, rule)
LAB_RULES: Dict[str, List[tuple]] = {
    "potassium": [
        (
            lambda v: v < 3.5,
            LabRule(
                "lab.potassium.low",
                "Hypokalemia",
                "high",
                "Potassium {value} mEq/L (< 3.5)",
                "K+ < 3.5 mEq/L",
            ),
        ),
        (
            lambda v: v > 5.5,
            LabRule(
                "lab.potassium.high",
                "Hyperkalemia",
                "high",
                "Potassium {value} mEq/L (> 5.5)",
                "K+ > 5.5 mEq/L",
            ),
        ),
    ],
    "inr": [
        (
            lambda v: v > 3.5,
            LabRule(
                "lab.inr.high",
                "Supratherapeutic INR",
                "high",
                "INR {value} (> 3.5) — bleeding risk",
                "INR > 3.5",
            ),
        ),
    ],
    "hba1c": [
        (
            lambda v: v > 9,
            LabRule(
                "lab.hba1c.high",
                "Poor glycemic control",
                "medium",
                "HbA1c {value}% (> 9%)",
                "HbA1c > 9%",
            ),
        ),
    ],
    "bnp": [
        (
            lambda v: v > 400,
            LabRule(
                "lab.bnp.high",
                "Elevated BNP",
                "medium",
                "BNP {value} pg/mL (> 400) — decompensation risk",
                "BNP > 400 pg/mL",
            ),
        ),
    ],
    "ef": [
        (
            lambda v: v < 40,
            LabRule(
                "lab.ef.low",
                "Reduced ejection fraction",
                "high",
                "EF {value}% (< 40%)",
                "EF < 40%",
            ),
        ),
    ],
    # Added for the Synthea-imported patient panel, which never carries
    # potassium/inr/bnp/ef — bmi/cholesterol/ldl are the only extra signal
    # it does provide, using standard ATP III / WHO cutoffs.
    "bmi": [
        (
            lambda v: 30 <= v < 40,
            LabRule(
                "lab.bmi.obese",
                "Obesity",
                "medium",
                "BMI {value} (≥ 30) — raises risk of diabetes, high blood pressure, and joint problems.",
                "WHO: BMI ≥ 30",
            ),
        ),
        (
            lambda v: v >= 40,
            LabRule(
                "lab.bmi.severe",
                "Severe obesity",
                "high",
                "BMI {value} (≥ 40) — sharply raises risk of diabetes, heart disease, "
                "and surgical/anesthesia complications.",
                "WHO: BMI ≥ 40",
            ),
        ),
    ],
    "cholesterol": [
        (
            lambda v: v >= 240,
            LabRule(
                "lab.cholesterol.high",
                "High total cholesterol",
                "medium",
                "Cholesterol {value} mg/dL (≥ 240)",
                "ATP III: total cholesterol ≥ 240 mg/dL",
            ),
        ),
    ],
    "ldl": [
        (
            lambda v: 160 <= v < 190,
            LabRule(
                "lab.ldl.high",
                "High LDL cholesterol",
                "medium",
                "LDL {value} mg/dL (≥ 160)",
                "ATP III: LDL ≥ 160 mg/dL",
            ),
        ),
        (
            lambda v: v >= 190,
            LabRule(
                "lab.ldl.veryhigh",
                "Very high LDL cholesterol",
                "high",
                "LDL {value} mg/dL (≥ 190)",
                "ATP III: LDL ≥ 190 mg/dL",
            ),
        ),
    ],
}


def _blood_pressure_threshold_flags(systolic: float, diastolic: float) -> List[Dict[str, str]]:
    if systolic >= 160 or diastolic >= 100:
        return [
            {
                "source": "lab",
                "rule_key": "lab.bp.hypertensive",
                "label": "Hypertensive range",
                "severity": "medium",
                "detail": f"BP {int(systolic)}/{int(diastolic)} (≥ 160/100)",
                "rule_source": "BP ≥ 160/100 mmHg",
                "kind": "clinical",
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


def _normalise_drug(name: str) -> str:
    """A drug name reduced to something two spellings of the same thing agree
    on: lowercased, dose and form stripped.

    Deliberately crude. This is a *screening* rule whose output a clinician
    reads, not a prescribing decision -- "Metformin 500mg" and "metformin"
    being recognised as the same drug is worth far more than the false
    positives a fuzzier match would add.
    """
    cleaned = _DOSE_RE.sub(" ", name.lower())
    cleaned = _FORM_RE.sub(" ", cleaned)
    return " ".join(cleaned.split())


#: The wrapper words a coded allergy list puts around the substance itself.
#: Synthea -- the corpus this repository actually imports -- records SNOMED
#: descriptions ("Allergy to penicillin", "Latex allergy", "Allergy to bee
#: venom"), and the substring rule below compares against a medication name,
#: which never contains them. Without this the whole allergy rule is inert on
#: every imported patient: it fires only for the hand-seeded "penicillin".
_ALLERGY_PREFIX_RE = re.compile(
    r"^(?:allergy\s+to|allergic\s+to|hypersensitivity\s+to|intolerance\s+to|sensitivity\s+to)\s+",
    re.IGNORECASE,
)
_ALLERGY_SUFFIX_RE = re.compile(r"\s+(?:allergy|hypersensitivity|intolerance)$", re.IGNORECASE)


def _normalise_allergen(name: str) -> str:
    """The substance an allergy entry is about, with the coding wrapper removed.

    Applied on top of `_normalise_drug`, not instead of it -- an entry may
    carry both a wrapper and a form ("Allergy to penicillin V tablet").
    """
    cleaned = _ALLERGY_PREFIX_RE.sub("", name.strip())
    cleaned = _ALLERGY_SUFFIX_RE.sub("", cleaned)
    return _normalise_drug(cleaned)


def _pair_key(drug_a: str, drug_b: str) -> str:
    a, b = sorted([_normalise_drug(drug_a), _normalise_drug(drug_b)])
    return f"{a}|{b}"


def _allergy_conflicts(medications: List[str], allergies: List[str]) -> List[Dict[str, str]]:
    """A medication on the list that the patient is recorded as allergic to.

    Substring matching on the normalised names: an allergy to "penicillin"
    catches "Penicillin V 500mg", and an allergy recorded as "sulfa" catches
    "sulfamethoxazole". Coded entries are unwrapped first (see
    `_normalise_allergen`), because a real allergy list says "Allergy to
    penicillin" and no medication name ever will. It will not catch cross-class reactions (a
    cephalosporin for a penicillin allergy) -- that needs a class table this
    codebase does not have, and inventing one here would be guessing at
    clinical content rather than encoding it.
    """
    flags: List[Dict[str, str]] = []
    seen: set[str] = set()

    for allergy in allergies:
        allergen = _normalise_allergen(allergy)
        if len(allergen) < 4:
            # Too short to match on without generating nonsense.
            continue
        for medication in medications:
            drug = _normalise_drug(medication)
            if allergen not in drug:
                continue
            key = f"allergy.conflict.{allergen}|{drug}"
            if key in seen:
                continue
            seen.add(key)
            flags.append(
                {
                    "source": "drug",
                    "rule_key": key,
                    "label": f"Allergy conflict: {medication}",
                    # Always high: this is a documented allergy against an
                    # active prescription, which is not a matter of degree.
                    "severity": "high",
                    "detail": (
                        f"{medication} matches a recorded allergy to {allergy}. Confirm before continuing."
                    ),
                    "rule_source": "patient's own recorded allergy list",
                    "kind": "clinical",
                }
            )
    return flags


def _duplicate_medications(medications: List[str]) -> List[Dict[str, str]]:
    """The same drug on the list twice under different spellings or doses."""
    by_drug: Dict[str, List[str]] = {}
    for medication in medications:
        drug = _normalise_drug(medication)
        if drug:
            by_drug.setdefault(drug, []).append(medication)

    return [
        {
            "source": "drug",
            "rule_key": f"drug.duplicate.{drug}",
            "label": f"Duplicate medication: {drug}",
            "severity": "medium",
            "detail": "Listed more than once: " + ", ".join(entries) + ".",
            "rule_source": "same active ingredient listed twice",
            "kind": "clinical",
        }
        for drug, entries in by_drug.items()
        if len(entries) > 1
    ]


def assess_patient_risk(
    lab_results: Optional[Dict[str, Any]],
    medications: Optional[List[str]] = None,
    allergies: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """All rule-based risk flags for a patient.

    `allergies` is optional and defaults to none, so every existing two-argument
    call site keeps working and simply gets no allergy flags -- the same
    degrade-quietly posture the rest of this module takes toward missing data.
    """
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
        drug_a, drug_b = interaction["pair"]
        flags.append(
            {
                "source": "drug",
                # Sorted, so "warfarin + aspirin" and "aspirin + warfarin" are
                # one finding rather than two alerts about the same fact.
                "rule_key": f"drug.interaction.{_pair_key(drug_a, drug_b)}",
                "label": f"Interaction: {drug_a} + {drug_b}",
                "severity": severity_map.get(interaction["severity"], "medium"),
                "detail": interaction["effect"],
                "rule_source": "curated interaction table (drug_safety_server)",
                "kind": "clinical",
            }
        )

    flags.extend(_allergy_conflicts(medications or [], allergies or []))
    flags.extend(_duplicate_medications(medications or []))

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
