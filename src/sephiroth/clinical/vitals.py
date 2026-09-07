"""Vital signs: what may be recorded, and what is worth saying about it.

Two bounds per vital, and the distinction between them is the whole design.

The **physiological** bound is what a human body can produce. A systolic
pressure of 900 is a typo or a broken device, never a patient, so it is
rejected — storing it would put a number in the chart that a later trend, rule
or average would take seriously.

The **clinical** range is what is normal. A systolic of 210 is outside it and is
*exactly* the reading this feature exists to capture, so it is stored and
flagged. A validator that refused it would be refusing the emergency.

Nothing here asks a model anything. Same posture as `sephiroth.safety.risk`:
the model explains, the rule decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


class VitalError(ValueError):
    """A vital that cannot be stored: an unknown key, or a value no body
    produces. Distinct from a value that is merely abnormal, which is stored
    and flagged."""


@dataclass(frozen=True)
class VitalSpec:
    key: str
    label: str
    unit: str
    #: What a body can produce. Outside this is a typo or a broken device.
    physiological: Tuple[float, float]
    #: What is normal. Outside this is a finding, not an error.
    clinical: Tuple[float, float]
    decimals: int = 0

    def format(self, value: float) -> str:
        return f"{value:.{self.decimals}f} {self.unit}".strip()


#: The vitals this product records. Adding one is a code change on purpose:
#: a vital nobody wrote a range for is a number nobody can interpret.
VITAL_SPECS: Dict[str, VitalSpec] = {
    spec.key: spec
    for spec in (
        VitalSpec("systolic", "Presión sistólica", "mmHg", (40, 300), (90, 130)),
        VitalSpec("diastolic", "Presión diastólica", "mmHg", (20, 200), (60, 85)),
        VitalSpec("heart_rate", "Frecuencia cardíaca", "lpm", (20, 250), (60, 100)),
        VitalSpec("respiratory_rate", "Frecuencia respiratoria", "rpm", (4, 60), (12, 20)),
        VitalSpec("temperature", "Temperatura", "°C", (30.0, 45.0), (36.0, 37.5), decimals=1),
        VitalSpec("oxygen_saturation", "Saturación de oxígeno", "%", (50, 100), (94, 100)),
        VitalSpec("weight", "Peso", "kg", (0.5, 400.0), (0.5, 400.0), decimals=1),
        VitalSpec("height", "Talla", "cm", (20, 250), (20, 250)),
        VitalSpec("glucose", "Glucometría", "mg/dL", (10, 900), (70, 140)),
        VitalSpec("pain_score", "Dolor (0-10)", "", (0, 10), (0, 3)),
    )
}

#: Vitals with no meaningful "normal": flagging every adult's weight as
#: abnormal would be noise, and noise is what makes people stop reading flags.
_NO_CLINICAL_RANGE = frozenset({"weight", "height"})


def validate_vitals(raw: Dict[str, Any]) -> Dict[str, float]:
    """Normalise a submitted vitals dict, or raise.

    Missing keys are simply absent — a visit that took a blood pressure and
    nothing else records a blood pressure and nothing else. An empty string is
    treated as absent too, because that is what an untouched form field sends.
    """
    if not isinstance(raw, dict):
        raise VitalError("vitals must be an object")

    unknown = sorted(set(raw) - set(VITAL_SPECS))
    if unknown:
        raise VitalError(f"unknown vital(s): {', '.join(unknown)}")

    out: Dict[str, float] = {}
    for key, value in raw.items():
        if value is None or value == "":
            continue
        spec = VITAL_SPECS[key]
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise VitalError(f"{spec.label}: '{value}' is not a number") from exc
        low, high = spec.physiological
        if not low <= number <= high:
            raise VitalError(
                f"{spec.label}: {spec.format(number)} is outside anything a body produces "
                f"({low:.{spec.decimals}f}–{spec.format(high)}). Check the device or the typing."
            )
        out[key] = round(number, spec.decimals)
    return out


@dataclass(frozen=True)
class VitalFinding:
    key: str
    label: str
    value: float
    display: str
    severity: str  # "high" | "medium"
    detail: str


def _severity(spec: VitalSpec, value: float) -> str:
    """How far outside normal, in units of the normal range's own width.

    Scaling by the range rather than by a fixed number keeps one rule for every
    vital: a saturation of 88% and a systolic of 180 are both "well outside",
    and a hand-written cutoff per vital would be ten numbers to keep in step.
    """
    low, high = spec.clinical
    span = max(high - low, 1e-6)
    distance = (low - value) if value < low else (value - high)
    return "high" if distance > span * 0.5 else "medium"


def vital_findings(vitals: Dict[str, Any]) -> List[VitalFinding]:
    """What is worth saying about these readings. Never raises.

    Reads whatever is stored, including values written before a spec changed,
    so a stored vital that no longer parses is skipped rather than taking down
    the read path.
    """
    findings: List[VitalFinding] = []
    for key, value in sorted((vitals or {}).items()):
        spec = VITAL_SPECS.get(key)
        if spec is None or key in _NO_CLINICAL_RANGE:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        low, high = spec.clinical
        if low <= number <= high:
            continue
        direction = "bajo" if number < low else "alto"
        findings.append(
            VitalFinding(
                key=key,
                label=spec.label,
                value=number,
                display=spec.format(number),
                severity=_severity(spec, number),
                # The range prints its unit once: "normal 90-130 mmHg", not
                # "normal 90 mmHg-130 mmHg", which is how a person writes it.
                detail=(
                    f"{spec.label} {direction}: {spec.format(number)} "
                    f"(normal {low:.{spec.decimals}f}–{spec.format(high)})"
                ),
            )
        )
    return findings


def format_vitals(vitals: Dict[str, Any]) -> str:
    """One line for the note. Blood pressure is rendered as a pair because
    that is how it is read aloud and written down; splitting it into two
    entries would make the note read like a machine wrote it."""
    if not vitals:
        return ""
    parts: List[str] = []
    systolic, diastolic = vitals.get("systolic"), vitals.get("diastolic")
    if systolic is not None and diastolic is not None:
        parts.append(f"PA {systolic:.0f}/{diastolic:.0f} mmHg")
    for key, value in vitals.items():
        if key in ("systolic", "diastolic") and systolic is not None and diastolic is not None:
            continue
        spec = VITAL_SPECS.get(key)
        if spec is None:
            continue
        try:
            parts.append(f"{spec.label} {spec.format(float(value))}".strip())
        except (TypeError, ValueError):
            continue
    return " · ".join(parts)


def parse_blood_pressure(text: str) -> Optional[Tuple[float, float]]:
    """ "120/80" -> (120.0, 80.0). Returns None for anything else.

    Exists because a clinician types a blood pressure as one thing, and a form
    with two boxes for it is a form that gets one box filled.
    """
    if not isinstance(text, str) or "/" not in text:
        return None
    left, _, right = text.partition("/")
    try:
        return float(left.strip()), float(right.strip())
    except ValueError:
        return None


__all__ = [
    "VITAL_SPECS",
    "VitalError",
    "VitalFinding",
    "VitalSpec",
    "format_vitals",
    "parse_blood_pressure",
    "validate_vitals",
    "vital_findings",
]
