"""Deterministic note scaffolding, and the note a visit renders into.

Two jobs, both pure.

`encounter_template(specialty)` gives a clinician the prompts their specialty
expects in each SOAP section — the thing a paper pad had printed on it. It is
not a model output and does not become one: a template a model wrote would vary
between visits, and the value of a template is that it does not.

`render_note(...)` turns a signed encounter into the text that goes in the
chart. It is the fallback when the model is unavailable *and* the format the
model is asked to produce, so a drafted note and a hand-written one read the
same on the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .vitals import format_vitals


@dataclass(frozen=True)
class SectionPrompts:
    subjective: str
    objective: str
    assessment: str
    plan: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "subjective": self.subjective,
            "objective": self.objective,
            "assessment": self.assessment,
            "plan": self.plan,
        }


_GENERAL = SectionPrompts(
    subjective="Motivo de consulta, evolución de los síntomas, antecedentes relevantes.",
    objective="Examen físico y hallazgos. Los signos vitales se agregan solos.",
    assessment="Impresión diagnóstica y su razonamiento.",
    plan="Conducta, estudios solicitados, ajustes de medicación, control.",
)

#: Specialty-specific prompts. Only the sections that genuinely differ are
#: overridden -- a table restating the general text under five headings would
#: be five places to edit for one change.
_BY_SPECIALTY: Dict[str, Dict[str, str]] = {
    "cardiology": {
        "subjective": (
            "Dolor torácico, disnea, palpitaciones, síncope. Clase funcional NYHA. "
            "Adherencia a antihipertensivos y anticoagulación."
        ),
        "objective": "Ruidos cardíacos, soplos, ingurgitación yugular, edemas, pulsos periféricos.",
        "plan": "Ajuste antihipertensivo o antiarrítmico, ECG, ecocardiograma, control de INR.",
    },
    "endocrinology": {
        "subjective": (
            "Control glucémico, hipoglucemias, adherencia, dieta y actividad física. "
            "Síntomas de neuropatía o alteración visual."
        ),
        "objective": "Peso, IMC, examen de pies, sitios de inyección.",
        "plan": "Ajuste de insulina u orales, HbA1c, perfil lipídico, fondo de ojo, control.",
    },
    "pediatrics": {
        "subjective": "Alimentación, sueño, desarrollo, esquema de vacunación, entorno familiar.",
        "objective": "Peso, talla y perímetro cefálico con percentiles. Examen por sistemas.",
        "plan": "Vacunas pendientes, pautas de alarma para los padres, control de crecimiento.",
    },
    "psychiatry": {
        "subjective": (
            "Estado de ánimo, sueño, apetito, ideación suicida (preguntar explícitamente), "
            "consumo de sustancias, adherencia."
        ),
        "objective": "Examen mental: apariencia, afecto, curso del pensamiento, juicio.",
        "plan": "Ajuste farmacológico, psicoterapia, red de apoyo, criterios de reconsulta.",
    },
}

#: The specialties a clinician can pick. `general` is always valid and is what
#: an unknown value degrades to -- a typo in a specialty must not cost someone
#: their note.
SPECIALTIES = ("general", *sorted(_BY_SPECIALTY))


def encounter_template(specialty: str = "general") -> SectionPrompts:
    overrides = _BY_SPECIALTY.get((specialty or "").strip().lower(), {})
    base = _GENERAL.as_dict()
    base.update(overrides)
    return SectionPrompts(**base)


_ORDER_LABELS = {
    "lab": "Laboratorio",
    "imaging": "Imagen",
    "referral": "Remisión",
    "followup": "Control",
    "medication": "Medicación",
}


def _order_line(order: Dict[str, Any]) -> str:
    label = _ORDER_LABELS.get(order.get("kind", ""), "Orden")
    detail = str(order.get("detail", "")).strip()
    days = order.get("due_in_days")
    when = f" (en {days} día{'s' if days != 1 else ''})" if days else ""
    return f"- {label}: {detail}{when}"


def render_note(
    *,
    chief_complaint: str = "",
    vitals: Optional[Dict[str, Any]] = None,
    subjective: str = "",
    objective: str = "",
    assessment: str = "",
    plan: str = "",
    patient_instructions: str = "",
    orders: Sequence[Dict[str, Any]] = (),
) -> str:
    """The encounter as chart text.

    Empty sections are omitted rather than printed with nothing under them: a
    note whose headings outnumber its content reads as though the visit was
    incomplete, when in fact one section simply had nothing to say.
    """
    blocks: List[str] = []
    if chief_complaint.strip():
        blocks.append(f"MOTIVO DE CONSULTA\n{chief_complaint.strip()}")

    vitals_line = format_vitals(vitals or {})
    objective_body = "\n".join(part for part in (vitals_line, objective.strip()) if part)

    for heading, body in (
        ("SUBJETIVO", subjective.strip()),
        ("OBJETIVO", objective_body),
        ("ANÁLISIS", assessment.strip()),
        ("PLAN", plan.strip()),
    ):
        if body:
            blocks.append(f"{heading}\n{body}")

    order_lines = [_order_line(o) for o in orders if str(o.get("detail", "")).strip()]
    if order_lines:
        blocks.append("ÓRDENES\n" + "\n".join(order_lines))

    if patient_instructions.strip():
        blocks.append(f"INDICACIONES AL PACIENTE\n{patient_instructions.strip()}")

    return "\n\n".join(blocks)


def fallback_draft(transcript: str, specialty: str = "general") -> Dict[str, str]:
    """The draft returned when no model is available.

    Deliberately does not try to guess which sentence is objective and which is
    a plan. It puts the clinician's own words where they can see them, under
    the headings their specialty expects, and leaves the sorting to the person
    who was in the room. A wrong guess costs more to correct than an honest
    blank costs to fill.
    """
    prompts = encounter_template(specialty)
    text = (transcript or "").strip()
    return {
        "subjective": text,
        "objective": "",
        "assessment": "",
        "plan": "",
        "_prompts": prompts.as_dict(),
    }


__all__ = [
    "SPECIALTIES",
    "SectionPrompts",
    "encounter_template",
    "fallback_draft",
    "render_note",
]
