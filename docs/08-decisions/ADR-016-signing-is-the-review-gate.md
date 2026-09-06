# ADR-016 — Signing is the review gate for a clinical note, not `PendingAction`

**Status:** Accepted · **Date:** 2026-09-06

## Context

SPEC-023 adds AI-assisted drafting of the encounter note. The requirement is
not in dispute: **no clinical content reaches the chart without a clinician
reading it.** A model that writes into a patient record unattended is the
failure this whole product is arranged to prevent.

The phase plan specified the mechanism as well as the requirement — route the
draft through the existing `PendingAction` approval queue, which already gates
patient messages and already has a router, an inbox, an expiry sweep and a
`ck_pending_action_requires_reviewer` constraint. Reusing it looks like the
cheap answer.

## Decision

The encounter's own `draft` → `signed` transition is the review gate. A note
draft never becomes a `PendingAction`.

`POST /api/encounters/{id}/draft-note` returns the drafted SOAP fields to the
caller and persists nothing. The clinician applies them with a `PATCH` if they
want them, edits them, and signs. Only signing writes a `ClinicalNote` and
creates the tasks the orders imply.

## Rationale

**`PendingAction` means "may I send this?", and a note is not sent.** The whole
reason `task_adapters.py` refuses to let a clinician complete an approval task
from the inbox is that closing a row is not the same act as consenting to
transmit a message to a patient. A note draft is transmitted to nobody. Putting
it in the same queue makes one Approve button mean two different things
depending on the row it is on, and the row a clinician clicks fastest is the
one they have seen fifty of.

**Approval is detached from the content; a signature is not.** A `PendingAction`
row can be approved by anyone with the clinician role, including someone who
never opened it — the constraint records *that* a reviewer existed, not that
they read anything. Signing an encounter is an action on the clinical content
itself, by the clinician who conducted the visit, recorded as `signed_by` and
`signed_at` against that content. It is the stronger guarantee, not a weaker
one.

**The unsigned state already enforces the requirement.** An unsigned encounter
has no `ClinicalNote`, contributes nothing to the timeline, files no tasks and
is invisible to the patient. There is no path by which unreviewed content
reaches the chart, because the thing that puts content in the chart *is* the
review. An approval queue would add a second gate in front of a gate.

**Mixing them degrades the queue that works.** The approvals inbox is currently
homogeneous: every row is a message to a human being, and a clinician reads it
knowing that. Adding note drafts makes it a queue of two unrelated kinds of
work, which is precisely the fragmentation SPEC-018 spent a phase undoing.

## Consequences

- Two review mechanisms exist in the product, and the distinction has to be
  learnable: **`PendingAction` gates what leaves for a patient; signing gates
  what enters the chart.** That line is easier to hold than one queue holding
  both.
- A model-drafted narrative that is never signed simply expires with its draft.
  Nothing sweeps it, and nothing needs to.
- `note_source` and `note_model` are persisted on the encounter, so a reader
  can see that a model wrote the first version of what they are reading. That
  provenance would have been on the `PendingAction` row otherwise, one join
  further from the content.
- If a deployment ever needs a *second* clinician to countersign, that is an
  additional field and transition on the encounter, not a repurposing of the
  approvals queue.

## Alternatives considered

**Route drafts through `PendingAction` as planned.** Rejected above: it
overloads the meaning of approval, detaches review from content, and dilutes a
queue that currently has one clear job.

**Persist the draft on the encounter and let the model write it directly.**
Simpler, and it makes the record briefly hold text no human has read. Even
though an unsigned encounter is invisible downstream, "the model wrote into the
patient's record and nobody had looked yet" is a sentence that should not be
true at any point. The draft stays in the response until a clinician acts.

**No AI drafting at all.** The safest option and the one that gives up the
phase's actual purpose. The risk it avoids is handled by the signature; the
time it costs is the reason the clinic wanted this.
