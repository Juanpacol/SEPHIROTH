"""What a push notification is allowed to say.

A payload is built from the table below, keyed on the notification's *type*. It
is never derived from `Notification.message`, which is written for the in-app
bell and correctly contains patient content.

The reason is that a push payload leaves this product's control completely: the
service worker hands it to the operating system, which renders it on a locked
screen, mirrors it to a watch, reads it aloud in a car, and files it in a
notification history that outlives the application. None of that is reached by
the PHI column encryption (ADR-014) or the egress gate (ADR-015).

"Be careful what you pass" is not a control — six modules call `send`, and every
one of them passes a message written for a different consumer. Building the
payload from a table means there is no path from the message to the payload at
all. See `docs/08-decisions/ADR-018-push-payloads-carry-no-phi.md`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

#: `(title, body, url)` per notification type. Every line has to be true of
#: every notification of that type and specific to none of them — that is the
#: test a new entry has to pass before it is written down.
SAFE_COPY: Dict[str, Tuple[str, str, str]] = {
    "alert_escalated": (
        "Alerta clínica sin resolver",
        "Una alerta lleva tiempo sin revisar.",
        "/tasks?category=alert",
    ),
    "clinical_alert": (
        "Nueva alerta clínica",
        "Hay una alerta nueva para revisar.",
        "/tasks?category=alert",
    ),
    "appointment_booked": (
        "Cita agendada",
        "Se agendó una cita nueva.",
        "/agenda",
    ),
    "appointment_reminder": (
        "Recordatorio de cita",
        "Tienes una cita próxima.",
        "/agenda",
    ),
    "appointment_unconfirmed": (
        "Cita sin confirmar",
        "Una cita próxima sigue sin confirmarse.",
        "/agenda",
    ),
    "result_shared": (
        "Resultado compartido",
        "Se compartió un resultado.",
        "/results",
    ),
    "result_critical": (
        "Resultado crítico",
        "Un resultado crítico está esperando revisión.",
        "/results",
    ),
    "waitlist_match": (
        "Cupo disponible",
        "Se liberó un cupo que alguien estaba esperando.",
        "/agenda",
    ),
    "followup_message": (
        "Mensaje de seguimiento por aprobar",
        "Hay un borrador esperando tu revisión.",
        "/approvals",
    ),
    "task_assigned": (
        "Tarea asignada",
        "Te asignaron una tarea clínica.",
        "/tasks?assignee=me",
    ),
    "consultation_needs_review": (
        "Consulta por revisar",
        "Una consulta necesita revisión clínica.",
        "/work",
    ),
}

#: Used for a type nobody has written copy for. Degrades toward *less*
#: information, never toward the message — a missing entry must not be a
#: silent route back to patient content.
_FALLBACK = ("SEPHIROTH", "Tienes algo pendiente por revisar.", "/work")

#: Exactly the keys a payload may carry. Asserted by the test rather than
#: merely intended, so an added field is a failing build.
PAYLOAD_KEYS = ("title", "body", "url", "tag", "notification_id")


def safe_copy_for(type_: str) -> Tuple[str, str, str]:
    return SAFE_COPY.get(type_, _FALLBACK)


def build_payload(*, notification_id: str, type_: str, url: Optional[str] = None) -> Dict[str, Any]:
    """The whole payload, from the type alone.

    `url` may be overridden by the caller because *where to land* is not
    patient content — it is a route, and the destination page enforces its own
    auth. Nothing else about the notification reaches this function, which is
    the point: there is no argument through which a message could arrive.

    `tag` is the type, not the patient. Grouping on a patient id would put an
    identifier in the payload, and because a matching `tag` *replaces* a
    notification, it would also mean a second critical alert silently replacing
    the first.
    """
    title, body, default_url = safe_copy_for(type_)
    return {
        "title": title,
        "body": body,
        "url": url or default_url,
        "tag": type_,
        # An opaque row id, so the client can mark it read on open. Useless
        # without an authenticated session, and it identifies a row rather
        # than a person.
        "notification_id": notification_id,
    }


__all__ = ["PAYLOAD_KEYS", "SAFE_COPY", "build_payload", "safe_copy_for"]
