---
id: SPEC-028
title: API Routers Reorganized by Domain
phase: 26
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: []
adrs: [ADR-019]
features: [F-113]
diagrams: []
---

# SPEC-028 — API Routers Reorganized by Domain

## 1. Summary

The last phase of the master plan, deliberately run after every other phase so
it would not overlap another structural migration. Twenty router modules move
from a single flat `platform/api/routers/` into four domain packages —
`clinical/`, `operations/`, `intelligence/`, `security/` — each under
`platform/api/`. No route, no behaviour, no response shape changes. `services/`
and `workflows/` are not moved; ADR-019 records why.

## 2. Motivation

`platform/api/routers/` had grown to twenty files with no organising principle
beyond alphabetical order in a directory listing: `agents.py` next to
`alerts.py` next to `approvals.py`, a consultation endpoint beside a clinical
alert beside a message-approval queue. Finding "where does the code for X
live" meant knowing the filename already, or scanning twenty unrelated names.

The master plan named this phase from the start and scoped it precisely:
reorganise `platform/` by domain, once everything else was closed — closing
everything else first was itself a deliberate decision, made explicitly by the
product owner, so that this reorganisation would not be racing another
structural change through the same files.

## 3. Goals

- **G-1** Each router lives under the domain its endpoints serve.
- **G-2** No behavioural change: same routes, same responses, same tests
  passing.
- **G-3** The move is mechanically verifiable, not just visually plausible —
  every import that could silently break is either converted to a form the
  move cannot affect, or explicitly updated and checked.

## 4. Non-Goals

- **NG-1** No reorganisation of `services/` or `workflows/`. ADR-019 explains:
  most of what lives there serves more than one domain by construction, and
  forcing a four-way split onto it would invent a boundary the code does not
  have.
- **NG-2** No reorganisation outside `platform/api/`. `src/sephiroth/`,
  `intelligence/`, `data/` already have their own internal organisation from
  earlier phases and are untouched.
- **NG-3** No route path changes. `/api/patients` is still `/api/patients`
  regardless of which Python package answers it.
- **NG-4** No rewriting of historical specs or migration docstrings that
  mention the old `platform/api/routers/...` paths. They are point-in-time
  records of what was true when written, the same convention every earlier
  spec in this series follows; only actively-maintained reference docs
  (`CLAUDE.md`, `ARCHITECTURE.md`) are updated to the new paths.

## 5. Definitions

- **Domain package** — one of `clinical/`, `operations/`, `intelligence/`,
  `security/` under `platform/api/`, each holding a `routers/` subpackage.

## 6. Contracts

### 6.1 Types

No schema change. No new Python types.

### 6.2 Interfaces

No route added, removed, or renamed. The mapping of file to domain:

| Domain | Routers |
|---|---|
| `clinical` | patients, encounters, alerts, results, result_reviews, portal, dashboard |
| `operations` | scheduling, tasks, approvals, followups, automation_memory, badges, notifications, push, internal |
| `intelligence` | agents, rag, medical |
| `security` | audit |

`main.py`'s import block and its `app.include_router(...)` calls are the only
place that names now differ; every prefix, tag, and dependency list is
unchanged.

### 6.3 State machine

`N/A`.

### 6.4 Errors

`N/A`.

### 6.5 Configuration

`N/A`.

## 7. Behaviour

- **B-1** Every route that existed before this phase MUST still resolve to the
  same handler, with the same guard, the same prefix, and the same response
  shape.
- **B-2** No router file MUST use a relative import (`from ..X import`,
  `from .. import X`) to reach `services/`, `workflows/`, `audit.py`,
  `paging.py`, `timeparse.py`, or the pure `scheduling.py` module — all such
  imports MUST be absolute (`from api.X import`), so a file's package depth
  never has to be recomputed by hand again.
- **B-3** Every module name recorded in `sephiroth.models.egress`'s PHI-seam
  lists MUST match the moved files' actual dotted paths — checked by the
  existing structural test, not merely updated by hand.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-028-01 | The full suite passes unchanged after the move (modulo the pre-existing, unrelated UTC-midnight flake) | B-1 | full suite, `PYTHONPATH=.:platform pytest -q` |
| AC-028-02 | No router file imports a sibling module by relative path | B-2 | `git grep -n "from \.\." platform/api/*/routers/*.py` (empty) |
| AC-028-03 | The PHI-seam structural test passes against the new paths | B-3 | `tests/test_phi_egress_gate.py::TestTheSeamListIsEnforcedNotJustWritten` |
| AC-028-04 | The datetime-contract structural test discovers routers across all four domain folders | B-1 | `tests/test_datetime_contract.py::TestTheContractIsUniform` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Regression | the whole backend suite, unchanged in outcome | every existing test file |
| Structural | no relative cross-package import survives in a router | manual grep, asserted at review time (no dedicated test — see §11 risk 2) |
| Structural | PHI seams and datetime-contract scans find the moved files | `test_phi_egress_gate.py`, `test_datetime_contract.py` |

## 10. Migration & Compatibility

No database migration — this phase touches only Python module layout. No
Alembic revision.

**A deployment pulling this change needs nothing beyond a normal restart.**
`platform/api/main.py` is the only file whose *import source* changed in a way
an operator would notice if they read logs closely (`api.clinical.routers`
instead of `api.routers`); the ASGI app object, its routes, and every response
shape are identical.

Historical spec files (`SPEC-009`, `SPEC-018`, `SPEC-021`, and others written
before this phase) still reference `platform/api/routers/<name>.py` in prose.
That is intentional — see NG-4 — and does not affect anything that runs.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | A future PR could reintroduce a relative cross-package import in a new router without anyone noticing until it breaks on the next move | Accepted for now, and worth a follow-up: a lint rule or a small structural test asserting no `platform/api/*/routers/*.py` file contains `from \.\.` would close this cheaply. Not added in this phase because it duplicates the manual check already performed line by line during the move (§9) and this phase's own scope is the move itself, not new tooling |
| 2 | `services/` and `workflows/` remain unorganised by domain, so "reorganise by domain" is only partially true of `platform/` | Recorded as a deliberate scope boundary in ADR-019, not an oversight. Extending the split there needs a real domain seam to exist first — several current modules (`task_derivation.py`, `channels.py`) read and write across domains by design, and inventing boundaries for them would cost more clarity than it added |
| 3 | Historical specs now describe file paths that no longer exist | Accepted per NG-4, matching the convention already established for every other phase's specs: a spec is a record of a decision made at a point in time, not a living reference kept in sync with the codebase forever |

## 12. References

- `docs/08-decisions/ADR-019-api-routers-by-domain-not-services-and-workflows.md`
  — what moved, what did not, and why.
- The original master plan (Spanish), phase 26: *"Reorganización por
  dominios ... cuando el resto esté cerrado, para no solapar dos migraciones
  estructurales."*

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
