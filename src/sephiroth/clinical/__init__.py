"""Clinical content that is decided by rules, not by a model.

Vital ranges and note templates live here for the same reason
`sephiroth.safety` does: they are clinical decisions expressed as code, and
code is reviewable in a way a prompt is not.
"""

from .templates import SPECIALTIES, encounter_template, fallback_draft, render_note
from .vitals import VITAL_SPECS, VitalError, format_vitals, validate_vitals, vital_findings

__all__ = [
    "SPECIALTIES",
    "VITAL_SPECS",
    "VitalError",
    "encounter_template",
    "fallback_draft",
    "format_vitals",
    "render_note",
    "validate_vitals",
    "vital_findings",
]
