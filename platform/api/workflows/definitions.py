"""The one place that imports every workflow-definition module, so their
self-registration into `registry.STEP_TYPES` (and, for modules with an
event subscriber, `sephiroth.workflows.events.SUBSCRIBERS` via
`subscriptions.py`) actually runs. Add a new definition module's import
here -- nowhere else needs to know it exists.

Importing this module is what makes `STEP_TYPES` non-empty; `engine.py`
imports it for exactly that reason. Safe to import in any order relative
to `registry.py` itself -- see that module's docstring for why no cycle
exists.
"""

from __future__ import annotations

from . import alert_escalation, appointment_reminder, handlers, patient_followup  # noqa: F401 -- imported for registration

__all__: list[str] = []
