# ADR-018 — A push payload carries fixed copy, never the notification's own text

**Status:** Accepted · **Date:** 2026-09-06

## Context

SPEC-025 adds web push so a clinician can be reached when the application is
closed. The obvious implementation is to send what the in-app notification
already says: `Notification.message` is a human-readable line, it is already
written, and reusing it means one string per event rather than two.

Those messages contain patient content. "Ana Gómez tiene un potasio de 6.2" is
exactly what makes the in-app notification useful, and exactly what must not
appear on a lock screen.

A push payload is not like other data this product handles. It is encrypted in
transit and the push service cannot read it — but it is decrypted by the
service worker and handed to the operating system, which renders it on a locked
device, mirrors it to a paired watch, reads it aloud through a car, and files it
in a notification history that survives the application being uninstalled. None
of that is under this product's control, and none of it is covered by the PHI
column encryption (ADR-014) or the egress gate (ADR-015).

## Decision

The payload is built from a **fixed table keyed on notification type**. It is
never derived from `Notification.message`, the patient, or any field of the
event that produced it.

```python
SAFE_COPY = {
    "alert_escalated": ("Alerta clínica sin resolver",
                        "Una alerta crítica lleva tiempo sin revisar."),
    ...
}
```

The payload is exactly `{title, body, url, tag, notification_id}`. `url` is a
route; opening it is what shows the clinician which patient, behind
`AuthGuard`, on a device they have unlocked.

The regression test is the one that matters: a notification whose `message`
contains a patient's name must produce a payload that does not.

## Rationale

**The failure is silent and permanent.** A payload that leaks is not an error
anyone sees. It is a correct-looking notification on a phone somebody left on a
table, and by the time it is noticed the copy is in an OS notification history
that no server-side deletion reaches. Compare that to the failure mode of fixed
copy: a clinician taps a notification that says less than they wanted, and the
application tells them the rest one second later.

**"Be careful at each call site" is not a control.** Six modules call
`NotificationChannel.send`, and every future one will pass a message written for
the in-app bell, where patient content is correct and expected. A design that
depends on each caller remembering that one consumer of that string is a lock
screen will fail on the seventh caller. A table the payload is *built from*
cannot fail that way: there is no path from the message to the payload.

**The tag is the notification type, not the patient.** Grouping on a patient id
would put an identifier in a field the OS treats as a string to compare — and
`tag` collisions replace notifications, so grouping on the patient would also
mean a second critical alert silently replaced the first.

**One thing genuinely is lost.** A clinician cannot triage from the lock screen:
"a critical alert needs review" does not say which patient or how bad. That is
the trade, and it is the right way round for a device that renders text to
whoever is holding it. SPEC-025 §11 risk 2 records it as a decision rather than
an oversight.

## Consequences

- Every notification type needs copy written for it. A type with no entry falls
  back to a generic line rather than to the message — degrading toward less
  information, never toward more.
- Push is a *signal*, and the application is the *content*. That shapes the
  interaction: the notification says something needs attention, the tap opens
  the thing.
- `notification_id` travels so the client can mark it read on open. It is an
  opaque UUID that identifies a row, not a person, and it is useless without an
  authenticated session.
- The same table is what a future email or SMS channel should build from, for
  the same reason — an SMS is rendered on the same lock screen.

## Alternatives considered

**Send `Notification.message`.** Rejected above: it is written to contain
patient content, and the leak is silent and unrecoverable.

**Redact the message before sending.** A redactor is a classifier, and ADR-015
already worked through why a classifier is the wrong control for exactly this
question: clinical language carries patient content with no name in it, and a
detector tuned not to refuse ordinary text will miss it. Building the payload
from fixed copy makes the question unnecessary rather than answering it badly.

**Let the user opt into detailed payloads.** Superficially reasonable — it is
their phone. But the person consenting is the clinician, and the data belongs to
the patient, who is not party to that choice. Consent to a risk should come from
whoever carries it.
