# ADR-019 — Routers move into domain packages; services and workflows stay put

**Status:** Accepted · **Date:** 2026-09-06

## Context

SPEC-028 is the last phase of the master plan, deferred to the end by the
product owner's own decision so it would not overlap another structural
migration. Its scope, as written: reorganise `platform/` by domain — `clinical/`,
`operations/`, `intelligence/`, `security/`.

By this point `platform/api/` holds three sibling trees: twenty router modules
(the HTTP surface), eight service modules (`encounter_service.py`,
`result_service.py`, `task_service.py`, ...), and twenty workflow modules (the
automation substrate — `engine.py`, `registry.py` — plus specific definitions
like `alert_escalation.py` and `no_show.py`). A literal reading of "reorganise
by domain" would move all three into four domain folders.

## Decision

**Only `routers/` moves.** Each of the twenty files goes into one of
`platform/api/{clinical,operations,intelligence,security}/routers/`, by which
bounded context its endpoints serve:

| Domain | Routers |
|---|---|
| `clinical` | patients, encounters, alerts, results, result_reviews, portal, dashboard |
| `operations` | scheduling, tasks, approvals, followups, automation_memory, badges, notifications, push, internal |
| `intelligence` | agents, rag, medical |
| `security` | audit |

`services/` and `workflows/` stay exactly where they are, at `platform/api/`.

## Rationale

**A router belongs to one bounded context. A service or a workflow definition
often does not.** `task_derivation.py` reads alerts, imaging studies, results
and encounters in the same sweep to decide what belongs in the inbox —
assigning it to `clinical/` or `operations/` is a coin flip, and the coin
lands differently depending on whether you are thinking about what it reads
(clinical facts) or what it produces (an operational queue). `channels.py`
sends a push notification regardless of which domain raised it.
`quiet_window_end` in `sephiroth.workflows.policy` is pure time arithmetic with
no domain at all. Forcing a four-way split onto modules that were built to be
shared would not clarify a boundary; it would invent one narrower than the
code and then violate it on the first cross-domain read.

**Routers are exactly where a domain reorg pays for itself.** An HTTP route is
a request for one thing, by one caller, and "which bounded context does
`POST /api/encounters/{id}/sign` belong to" has exactly one honest answer. The
router layer is also where a newcomer — or an agent extending the API — starts
reading, so it is where a domain-labelled folder does the most good per file
moved.

**The blast radius is bounded and it is real.** Even routers-only, this touches
main.py's import block, twelve test files that import a router module directly
for HTTP-level tests, the two structural tests that walk the filesystem
(`test_datetime_contract.py`'s per-router-file scan,
`test_phi_egress_gate.py`'s reaching-a-module scan), the PHI-seam lists in
`sephiroth.models.egress` (three router module names are load-bearing strings
there, not just documentation), and one lazy cross-import
(`task_derivation.py` reaching into `dashboard.py` for
`_evolution_deteriorating`). Extending the same move to `services/` and
`workflows/` would roughly triple that surface for files whose domain
assignment is already disputed above — more risk, spent on the part of the
tree least suited to a domain split.

**Routers already imported everything else by relative path, inconsistently.**
Twelve of twenty used `from ..services import`, `from ..workflows.X import`;
four already used the absolute `from api.services import` form. Moving a
router one level deeper breaks every relative import's depth (`..` now means
something one level higher than before) but changes nothing for an absolute
one. So the reorg's own mechanics favour the router layer: converting the
twelve holdouts to absolute imports first, then moving files, turns "adjust
every relative import's dot-count by hand" into "verify zero relative imports
remain" — a much cheaper and more checkable step, done as its own commit
before any file moved.

## Consequences

- `platform/api/services/` and `platform/api/workflows/` are addressed the
  same way from every router, regardless of which domain folder it lives in:
  `from api.services.X import ...`, `from api.workflows.X import ...`. A
  router's domain says what it serves, not where its dependencies live.
- The one router-to-router reach (`task_derivation.py` → `dashboard.py`) is
  now an absolute import naming `api.clinical.routers.dashboard` explicitly —
  more honest than the relative `..routers.dashboard` it replaced, which said
  nothing about which domain it was reaching into.
- `sephiroth.models.egress.PHI_SEAMS`/`PHI_DOWNSTREAM` name router modules by
  their new dotted paths. The enforcement test in `test_phi_egress_gate.py`
  recomputes module names from the filesystem on every run, so a future move
  is caught immediately if these lists are not updated with it — which is
  exactly what happened while writing this ADR: the first pass reorganised
  files before updating these dictionaries, and the existing test refused to
  pass until they matched.
- `services/` and `workflows/` remain open questions for a later, narrower
  ADR if a genuine seam appears inside them (for instance, if the workflow
  substrate — `engine.py`, `registry.py`, the outbox — is ever extracted from
  the domain-specific step definitions that register against it). Nothing here
  forecloses that; it simply was not this phase's job to invent a boundary
  that the code does not yet have.

## Alternatives considered

**Move everything — routers, services, workflows — into the four domains.**
Rejected above: most service and workflow modules read and write across
domain lines by design, and forcing a split would either scatter one
cohesive concern across four folders or produce a "shared" fifth folder that
is where everything contested ends up — which is the flat structure this ADR
is trying to avoid, wearing a domain label.

**Leave everything flat and call the phase done by writing this ADR alone.**
Rejected: the master plan's own wording commits to a domain reorganisation,
and the router layer is the one place in `platform/api/` where that
reorganisation is unambiguous and low-risk. Skipping it would leave the
plan's last phase undone for no reason stronger than "the rest is harder."

**A `shared/` or `common/` package for services and workflows, to make the
domain split look complete.** Rejected: naming something "shared" is not a
domain decision, it is the absence of one, and dressing that up as the fourth
member of a four-domain split would make the reorg look more finished than it
is.
