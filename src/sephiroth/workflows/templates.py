"""Deterministic text for the messages automation proposes.

A follow-up step used to create its `PendingAction` with `draft_text=""`, so
the approvals inbox could show a row with nothing in it and a button that says
"generate draft" — asking a clinician to babysit the automation before they can
review its output.

The template is not a placeholder for the LLM version; it is the floor. A
clinician can approve it as-is, and it is what remains when the model is
unreachable, which on a local-first deployment is a normal Tuesday rather than
an incident. `approvals.py` may still upgrade it to a drafted version on
request — that path sets `draft_source="llm"`.

Pure: no session, no settings, no I/O. That is what lets the step call it
without breaking SPEC-009's rule that a tick never invokes a model.
"""

from __future__ import annotations

#: Day-number -> what the message is actually asking about. Keyed on the step
#: key the follow-up definition already uses.
_CHECK_INTENT = {
    "day3": "cómo te has sentido en estos primeros días",
    "day7": "cómo va tu evolución en la primera semana",
    "day30": "cómo te encuentras un mes después",
}

_DEFAULT_INTENT = "cómo has seguido"


def render_followup_draft(check_key: str, instructions: str = "", first_name: str = "") -> str:
    """A complete, sendable follow-up message.

    `instructions` is what the clinician wrote when starting the plan — the
    thing they said they wanted watched. Including it is what makes the draft
    specific enough to send rather than generic enough to need rewriting.
    """
    greeting = f"Hola {first_name.strip()}," if first_name.strip() else "Hola,"
    intent = _CHECK_INTENT.get(check_key, _DEFAULT_INTENT)

    lines = [
        greeting,
        "",
        f"Te escribimos desde la consulta para saber {intent}.",
    ]
    if instructions.strip():
        lines.append(f"En particular, nos interesa saber sobre: {instructions.strip()}.")
    lines += [
        "",
        "Si algo ha empeorado o tienes una duda, respóndenos por este medio.",
    ]
    return "\n".join(lines)


__all__ = ["render_followup_draft"]
