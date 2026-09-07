"""Turning what the clinician said into a structured note.

The model does exactly one job here: sort free text into SOAP sections. It does
not diagnose, does not add facts, and does not decide anything — the prompt says
so and the degrade path assumes it will sometimes fail anyway.

Nothing in this module writes to the database. `/draft-note` returns the draft
to the caller and the clinician applies it with a `PATCH` if they want it, so a
model's text never sits in a patient's record before a human has looked at it
(ADR-016).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set

from sephiroth.clinical.templates import encounter_template, fallback_draft
from sephiroth.models import LLMUnavailableError, get_llm_client
from sephiroth.models.egress import assert_phi_egress_allowed
from sephiroth.safety.output_safety import check_input

logger = logging.getLogger(__name__)

#: The four sections, and nothing else. `additionalProperties: False` is what
#: stops a model from inventing a fifth section that the UI would silently
#: drop -- schema-constrained decoding makes this a structural guarantee on
#: providers that support it, and a cheap validation everywhere else.
DRAFT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "subjective": {"type": "string"},
        "objective": {"type": "string"},
        "assessment": {"type": "string"},
        "plan": {"type": "string"},
    },
    "required": ["subjective", "objective", "assessment", "plan"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = """Eres un asistente de documentación clínica. Tu única tarea es
reorganizar las notas que el médico ya escribió en las cuatro secciones SOAP.

Reglas absolutas:
- NO agregues información que no esté en el texto. Ni diagnósticos, ni dosis, ni
  hallazgos, ni signos vitales.
- NO infieras. Si el texto no dice a qué sección pertenece algo, déjalo en
  subjective.
- NO opines sobre el manejo clínico ni sugieras conductas.
- Conserva las palabras del médico siempre que sea posible. Corrige solo
  puntuación y ortografía evidente.
- Si una sección no tiene contenido en el texto, devuélvela como cadena vacía.
  Una sección vacía es correcta; inventarla no lo es.

Responde solo con el objeto JSON pedido."""


def _user_prompt(transcript: str, specialty: str) -> str:
    prompts = encounter_template(specialty).as_dict()
    guide = "\n".join(f"- {name}: {text}" for name, text in prompts.items())
    return f"Especialidad: {specialty}\n\nQué va en cada sección:\n{guide}\n\nNotas del médico:\n{transcript}"


_WORD_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)

#: Below this share of words already present in the clinician's own text, a
#: section is reported as containing added content.
_GROUNDED_FRACTION = 0.6


def _words(text: str) -> Set[str]:
    return {match.group(0).lower() for match in _WORD_RE.finditer(text or "")}


def added_content_sections(draft: Dict[str, str], transcript: str) -> List[str]:
    """Sections the model appears to have written rather than reorganised.

    The system prompt forbids adding information. A small local model does not
    reliably obey that -- verified during this phase's development: asked to
    sort "cefalea de 3 días, PA 210/120, inicio losartán", `qwen2.5:3b` produced
    an assessment of "Hipertensión arterial" and a plan including a brain scan.
    Both are plausible and neither was in the text.

    The signature is the guarantee (ADR-016), and the clinician reads before
    signing. This is the cheap deterministic help that makes reading easier:
    a section whose vocabulary is largely absent from the source is flagged so
    the UI can mark it, rather than presenting every section as equally
    faithful.

    Word overlap, not meaning -- the same posture as ADR-006's low-overlap
    downgrade in claim verification. It over-flags a section that paraphrases
    heavily, which costs a second look; it under-flags a fabrication built from
    the source's own words, which is why it is an aid to review and not a
    substitute for it.
    """
    source = _words(transcript)
    flagged: List[str] = []
    for section in ("subjective", "objective", "assessment", "plan"):
        content = _words(draft.get(section, ""))
        if not content:
            continue
        grounded = len(content & source) / len(content)
        if grounded < _GROUNDED_FRACTION:
            flagged.append(section)
    return flagged


def _clean(payload: Any, transcript: str, specialty: str) -> Dict[str, str]:
    """Keep only the four expected string fields.

    A malformed payload degrades to the template rather than raising: the
    clinician asked for help organising their text, and the failure mode of
    that request should be "no help", never "your text is gone".
    """
    if not isinstance(payload, dict):
        return {k: v for k, v in fallback_draft(transcript, specialty).items() if k != "_prompts"}
    draft = {key: str(payload.get(key, "") or "").strip() for key in DRAFT_SCHEMA["properties"]}
    if not any(draft.values()):
        return {k: v for k, v in fallback_draft(transcript, specialty).items() if k != "_prompts"}
    return draft


async def draft_encounter_note(transcript: str, specialty: str = "general") -> Dict[str, Any]:
    """Sort `transcript` into SOAP sections.

    Always returns a usable draft (B-9). Every failure — no model, a refusal on
    PHI-egress grounds, a timeout, a malformed payload — degrades to the
    clinician's own text under the right headings, with `source` saying which
    happened so the UI can be honest about it.
    """
    text = (transcript or "").strip()
    if not text:
        return {"source": "template", "model": None, **_clean(None, "", specialty)}

    # The same heuristic the consultation path applies to a query. This text is
    # free-form, reaches a model prompt, and — unlike a consultation — gets
    # there from a routine click during a visit.
    if check_input(text):
        logger.warning("encounter draft input matched an injection pattern; using the template")
        return {
            "source": "template",
            "model": None,
            "degraded_reason": "injection_heuristic",
            **_clean(None, text, specialty),
        }

    client = get_llm_client()
    try:
        # A visit's free text is patient content (SPEC-022 §6.5). On the
        # default local provider this never refuses, because nothing leaves.
        assert_phi_egress_allowed(client, "encounter note drafting")
        payload = await client.generate_json(
            _user_prompt(text, specialty), DRAFT_SCHEMA, system_prompt=_SYSTEM_PROMPT
        )
    except LLMUnavailableError as exc:
        logger.info("note drafting unavailable (%s); returning the template draft", exc)
        return {
            "source": "template",
            "model": None,
            "degraded_reason": str(exc),
            **_clean(None, text, specialty),
        }
    except Exception:
        logger.exception("note drafting failed; returning the template draft")
        return {
            "source": "template",
            "model": None,
            "degraded_reason": "provider_error",
            **_clean(None, text, specialty),
        }

    draft = _clean(payload, text, specialty)
    model = getattr(client, "model", None)
    # `_clean` degrades to the template on a malformed payload, and calling
    # that "llm" would attribute the clinician's own text to a model.
    used_model = draft.get("subjective") != text or any(
        draft[key] for key in ("objective", "assessment", "plan")
    )
    return {
        "source": "llm" if used_model else "template",
        "model": model if used_model else None,
        # Which sections to look at hardest. Empty when the model only
        # reorganised, which is what it was asked to do.
        "added_content": added_content_sections(draft, text) if used_model else [],
        **draft,
    }


__all__ = ["DRAFT_SCHEMA", "added_content_sections", "draft_encounter_note"]
