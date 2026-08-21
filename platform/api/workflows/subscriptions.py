"""Wires event subscribers into `sephiroth.workflows.events.SUBSCRIBERS`.
Called once from `api.main`'s lifespan, after `init_db()`. Kept as its
own module (rather than each definition module self-registering on
import) so the wiring is one visible list, the same reasoning as
`src/sephiroth/tools/servers.py::SERVERS`.
"""

from __future__ import annotations

from sephiroth.workflows.events import CLINICAL_ALERT, SUBSCRIBERS

from . import alert_escalation

_REGISTERED = False


def register_subscriptions() -> None:
    """Idempotent -- safe to call more than once (e.g. across test
    client instances reusing the same process)."""
    global _REGISTERED
    if _REGISTERED:
        return
    SUBSCRIBERS.setdefault(CLINICAL_ALERT, []).append(alert_escalation.on_clinical_alert)
    _REGISTERED = True


__all__ = ["register_subscriptions"]
