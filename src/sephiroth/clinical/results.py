"""How abnormal a result is, decided by arithmetic.

Three levels, in the order they are checked, because the order is the whole
rule:

1. **critical** — one of `sephiroth.safety.risk.LAB_RULES` fires. Those
   thresholds already exist and already drive alerts; a second table of clinical
   cutoffs would be two opinions that agree until one is edited.
2. **abnormal** — outside the reference range that came with the result, or
   outside `REFERENCE_RANGES` when none did.
3. **normal** — inside it.

An unknown test is `unclassified`, recorded and shown, never refused. A clinic
that runs a test this product has no range for still has the result, and losing
it to protect a taxonomy would be the wrong trade.

Nothing here asks a model anything (SPEC-024 NG-3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sephiroth.safety.risk import LAB_RULES

#: Severities, most to least urgent. `unclassified` is deliberately not on the
#: scale: it is an absence of information, not a degree of concern, and sorting
#: it between `normal` and `abnormal` would invent a judgement.
SEVERITIES = ("critical", "abnormal", "normal", "unclassified")

#: Adult reference ranges for the tests this product knows. Small on purpose
#: and honest about it (SPEC-024 §11 risk 3): the gap shows up as
#: `unclassified` in the inbox, which is also the list of ranges worth adding.
#:
#: Keys are the normalised test name (`_normalise`), so "Potassium", "potasio"
#: and "K+" reach the same entry.
REFERENCE_RANGES: Dict[str, Tuple[float, float]] = {
    "potassium": (3.5, 5.0),
    "sodium": (135.0, 145.0),
    "creatinine": (0.6, 1.3),
    "glucose": (70.0, 100.0),
    "hba1c": (4.0, 5.7),
    "inr": (0.8, 1.2),
    "hemoglobin": (12.0, 17.0),
    "platelets": (150.0, 450.0),
    "leukocytes": (4.0, 11.0),
    "tsh": (0.4, 4.0),
    "ldl": (0.0, 100.0),
    "alt": (0.0, 40.0),
    "ast": (0.0, 40.0),
    "calcium": (8.5, 10.5),
    "magnesium": (1.7, 2.2),
    # These four exist because `LAB_RULES` has a critical threshold for each,
    # and a test the product knows is dangerous at one value must not fall
    # through to `unclassified` at another. A test enforces the pairing.
    "bnp": (0.0, 100.0),
    "cholesterol": (0.0, 200.0),
    "bmi": (18.5, 25.0),
    "ef": (55.0, 70.0),
}

#: Spellings a clinic actually types, mapped onto the keys above. Kept as
#: aliases rather than as extra range entries so a range is defined once.
_ALIASES = {
    "k": "potassium",
    "k+": "potassium",
    "potasio": "potassium",
    "na": "sodium",
    "na+": "sodium",
    "sodio": "sodium",
    "creatinina": "creatinine",
    "glucosa": "glucose",
    "glicemia": "glucose",
    "a1c": "hba1c",
    "hemoglobina": "hemoglobin",
    "hb": "hemoglobin",
    "plaquetas": "platelets",
    "leucocitos": "leukocytes",
    "calcio": "calcium",
    "magnesio": "magnesium",
    "colesterol ldl": "ldl",
}


def _normalise(test_name: str) -> str:
    cleaned = " ".join((test_name or "").lower().split())
    return _ALIASES.get(cleaned, cleaned)


@dataclass(frozen=True)
class Classification:
    severity: str
    #: Why, in one line a clinician can check. A severity nobody can trace back
    #: to a threshold is one they have to take on faith.
    reason: str
    #: The rule that fired, when one did -- the same key the alert carries, so
    #: a result and its alert can be tied together.
    rule_key: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None

    @property
    def is_abnormal(self) -> bool:
        return self.severity in ("abnormal", "critical")

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


def _critical_rule(test_name: str, value: float):
    for predicate, rule in LAB_RULES.get(_normalise(test_name), []):
        try:
            if predicate(value):
                return rule
        except (TypeError, ValueError):  # pragma: no cover - a rule that cannot judge
            continue
    return None


def classify_lab(
    test_name: str,
    value: float,
    *,
    reference_low: Optional[float] = None,
    reference_high: Optional[float] = None,
) -> Classification:
    """How concerning this number is.

    A range supplied with the result wins over the built-in one: the laboratory
    that ran the assay knows its own reference interval, and overriding it with
    a table in this repository would be this product second-guessing the lab.
    """
    rule = _critical_rule(test_name, value)
    if rule is not None:
        return Classification(
            severity="critical",
            # `LabRule.source`/`.key` (SPEC-021's dedup identity) aren't in
            # this branch's risk.py yet -- restoring that is a separate
            # phase. `.detail` (with the value filled in) is the one field
            # both versions have that still names the threshold that fired.
            reason=rule.detail.format(value=value),
            rule_key=None,
            reference_low=reference_low,
            reference_high=reference_high,
        )

    low, high = reference_low, reference_high
    if low is None or high is None:
        known = REFERENCE_RANGES.get(_normalise(test_name))
        if known is None:
            return Classification(
                severity="unclassified",
                reason=f"No reference range on file for '{test_name}'.",
            )
        low, high = known

    if value < low:
        return Classification(
            severity="abnormal",
            reason=f"{value} below the reference range ({low}–{high}).",
            reference_low=low,
            reference_high=high,
        )
    if value > high:
        return Classification(
            severity="abnormal",
            reason=f"{value} above the reference range ({low}–{high}).",
            reference_low=low,
            reference_high=high,
        )
    return Classification(
        severity="normal",
        reason=f"Within the reference range ({low}–{high}).",
        reference_low=low,
        reference_high=high,
    )


#: `ImagingStudy.severity` is already a clinical judgement made when the study
#: was read. It is translated rather than re-derived -- there is no number to
#: compare, and inventing a second opinion from a free-text finding would be
#: exactly the model-driven classification NG-3 rules out.
_IMAGING_SEVERITY = {"critical": "critical", "review": "abnormal", "none": "normal"}


def classify_imaging(severity: str, finding_summary: str = "") -> Classification:
    mapped = _IMAGING_SEVERITY.get((severity or "").lower())
    if mapped is None:
        return Classification(severity="unclassified", reason=f"Unknown study severity '{severity}'.")
    reason = finding_summary.strip() or f"Study read as '{severity}'."
    return Classification(severity=mapped, reason=reason[:300])


#: What a result of each severity is worth as inbox work. `critical` inherits
#: the one-hour SLA; `abnormal` gets a day, because the point of surfacing it is
#: that it is easy to miss, not that it is an emergency.
TASK_SEVERITY_BY_RESULT = {"critical": "critical", "abnormal": "medium", "unclassified": "low"}


def deserves_a_task(classification: Classification) -> bool:
    """A normal result is not work.

    Filing one anyway is how an inbox teaches people to skim, and the results
    that get missed are missed in an inbox nobody reads carefully.
    """
    return classification.severity in TASK_SEVERITY_BY_RESULT


__all__ = [
    "REFERENCE_RANGES",
    "SEVERITIES",
    "TASK_SEVERITY_BY_RESULT",
    "Classification",
    "classify_imaging",
    "classify_lab",
    "deserves_a_task",
]
