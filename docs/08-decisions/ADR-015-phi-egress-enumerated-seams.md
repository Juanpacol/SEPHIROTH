# ADR-015 — PHI egress is an enumerated seam list, not a classifier

**Status:** Accepted · **Date:** 2026-09-06

## Context

The product's privacy notice says clinical text and medical images are sent to
Google's Gemini API. That has been accurate and unenforceable: nothing in the
codebase could be configured to make it false. SPEC-022 adds `ai_allow_phi`,
the switch that decides whether patient-derived content may reach a provider
outside the deployment.

The switch needs an enforcement point, and there are two shapes it could take.

**Inspect the payload.** Wrap the client, look at each outbound prompt, decide
whether it contains patient data, refuse if it does. It catches every call site
automatically, including ones written after the switch exists.

**Enumerate the seams.** Name the call sites that are known to carry patient
content, and gate exactly those.

## Decision

Enumerate. `SPEC-022 §6.5` lists the seams — consultation execution, timeline
extraction from a clinical note, medical-image description in both its
blocking and streaming forms, and patient-message drafting — and
`ai_allow_phi` is checked at each, before any request is built.

A test enforces the list rather than trusting it: it walks the modules that
reach an LLM client and fails when one appears that is on none of three lists —
gated seams, modules reachable only through a gated seam, or modules explicitly
recorded as carrying no patient content. A new seam therefore fails the build
instead of shipping ungated.

The check justified itself on its first run: it found that
`platform/api/routers/medical.py` streams a medical image straight to the
client rather than going through `vision_server`, so the seam list written by
hand a few minutes earlier was already incomplete. That is the failure mode
this ADR predicted, caught by the mechanism this ADR chose, before the code
shipped.

## Rationale

A classifier is a probabilistic answer to a question that has to be answered
correctly every time. Patient data does not announce itself: a query reading
"56-year-old on warfarin with an INR of 4.8, is the dose safe" contains no
name, no identifier, and no keyword a detector would match, yet it is exactly
the content the switch exists to hold back. A detector tuned to catch it either
matches most clinical language — refusing the guideline lookups that are
legitimately fine to send — or it misses cases like this one.

The failure modes are not symmetric. An over-broad detector is visible: someone
reports a refused request and it gets fixed. A detector that misses is silent,
and what it costs is patient data at a third party, discovered later or not at
all. A control whose failures are invisible is worse than a narrower control
whose boundaries are written down, because it invites trust it has not earned.

The enumerated list is honest about its own limits in a way a classifier cannot
be. A handful of entries can be read, reviewed by someone who is not a
programmer, and checked against the code. "The model decided it looked safe"
cannot.

The list's real weakness — a seam added later and forgotten — is the one part
of this that automation handles well, because "does this module call an LLM
client" is a structural question with an exact answer, unlike "does this string
contain PHI". So the check that runs in CI is the one a machine can actually
get right.

## Consequences

- Adding a call site that reaches a model means adding it to the list or
  recording why it carries no patient content. That is friction, and it is the
  intended kind: it puts the question in front of someone at the moment it can
  still be answered cheaply.
- `ai_allow_phi=false` is inert against a local provider. Nothing leaves the
  deployment, so there is nothing to gate — the flag is about egress, not about
  whether AI runs.
- The flag removes one specific exposure. It is not a compliance claim, and
  SPEC-022 NG-5 says so: content not leaving for a model vendor is one property
  among many that HIPAA and GDPR ask about.
- If the seam list ever grows past what a person can hold in their head, that
  is evidence the architecture has spread model access too widely — a signal
  worth having, and one a payload inspector would have hidden.

## Alternatives considered

**Wrap the client and inspect prompts.** Rejected above: silent misses on
clinical language that carries no identifiers.

**Refuse all remote providers when the flag is off.** Simpler and stricter, but
it conflates two things a deployment legitimately separates. Evidence retrieval
over a public guideline corpus and the abstention judge run on synthetic text;
forbidding them alongside the PHI seams would push operators to turn the flag
off entirely to get anything working, which is how a safety control becomes the
thing everyone disables.

**Per-seam settings instead of one flag.** More expressive, and nobody would
configure it correctly. One switch with a written list of what it covers is
auditable; four switches are a matrix whose combinations nobody has reasoned
about.
