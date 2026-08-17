---
id: SPEC-000
title: Spec Process
phase: 0
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-08-16
updated: 2026-08-16
supersedes: []
superseded_by: null
depends_on: []
adrs: []
features: [F-020]
diagrams: []
---

# SPEC-000 — Spec Process

## 1. Summary

Defines how SEPHIROTH specifications are written, versioned, reviewed, and
retired. This is the meta-spec: every other `SPEC-00N` conforms to the template
in §6.1 and the lifecycle in §6.2. It is normative.

## 2. Motivation

The repository grew a working clinical application (260 tests, 88% coverage)
whose architecture documentation drifted from reality — `docs/INTEGRATION_GUIDE.md`
referenced an `agents/graph/` package that never existed, LlamaIndex that was
never used, and three example files that are not on disk. `CLAUDE.md` documented
an agent attribute `system_prompt` when the real attribute is `role_prompt`
(`intelligence/agents/base.py:26`).

Prose documentation drifts because nothing fails when it lies. Spec-Driven
Development fixes this by making the spec the artifact tests are written from,
and by making a subset of every spec mechanically checkable.

## 3. Goals

- **G-1** A contributor can write a complete test file from a spec alone, before
  any implementation exists.
- **G-2** A contract change that is not reflected in its spec fails CI.
- **G-3** A spec's status accurately reflects whether its behaviour is live.
- **G-4** Normative documents (specs) and descriptive documents (guides) never
  share a directory, so neither rots into the other.

## 4. Non-Goals

- **NG-1** This spec does not define documentation *prose* style, only structure.
- **NG-2** It does not mandate specs for bug fixes, dependency bumps, or any
  change that alters no contract in §6 of an existing spec.
- **NG-3** It does not cover the evaluation/research documents
  (`docs/05-evaluation/`, `docs/07-research/results.md`) — those are out of the
  architecture migration's scope.

## 5. Definitions

- **Contract** — a type, interface signature, wire format, or state transition
  that something outside the defining module depends on.
- **Normative** — a statement whose violation is a defect. Marked with RFC-2119
  keywords (MUST / MUST NOT / SHOULD / MAY).
- **Acceptance Criterion (AC)** — a normative statement expressed so that a test
  can assert it mechanically. If it cannot be asserted, it is a Behaviour (§7),
  not an AC.
- **Guide** — descriptive prose in `docs/01-architecture/` etc. Always mutable,
  never normative, always cites its governing spec.

## 6. Contracts

### 6.1 The spec template

Every `SPEC-00N` MUST contain sections 1–12 below, in order, with these exact
headings. Sections that do not apply MUST be present and contain the single
word `N/A` with a one-line reason — silence is ambiguous, an explicit `N/A` is
a decision.

````markdown
---
id: SPEC-00N
title: <Component>
phase: N
version: 0.1.0
status: Draft
authors: [<handle>]
created: YYYY-MM-DD
updated: YYYY-MM-DD
supersedes: []
superseded_by: null
depends_on: [SPEC-00M]
adrs: [ADR-00X]
features: [F-0XX]
diagrams: [DN]
---

# SPEC-00N — <Component>

## 1. Summary
One paragraph. What capability this phase adds.

## 2. Motivation
Why the current system cannot do this. MUST cite the concrete limitation as
`path/to/file.py:LINE`, not an abstraction.

## 3. Goals
- G-1 ...   (each goal maps to at least one acceptance criterion)

## 4. Non-Goals
- NG-1 ...  (anything a reader might reasonably assume is in scope)

## 5. Definitions
Only terms whose meaning here is narrower than in `docs/00-project/glossary.md`.

## 6. Contracts

### 6.1 Types
Module path, then the Pydantic/dataclass definition verbatim (normative), then
a table:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|

### 6.2 Interfaces
Protocol / ABC signatures verbatim, including async-ness and exceptions raised.

### 6.3 State machine
`N/A` or: a link to the canonical diagram plus a transition table. **The table,
not the diagram, is normative.**

| From | Event | To | Guard |
|---|---|---|---|

### 6.4 Errors
Exception hierarchy, and which failure-taxonomy value each maps to.

### 6.5 Configuration
New settings keys, types, defaults, validation rules.

## 7. Behaviour
Numbered normative statements using RFC-2119 keywords.
- B-1 The runtime MUST NOT ...

## 8. Acceptance Criteria
Machine-checkable only.

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-00N-01 | ... | B-1 | `tests/test_x.py::test_y` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|

## 10. Migration & Compatibility
What of the legacy tree this shadows; the shim module path; the removal
condition. A shim MUST declare the phase in which it is deleted.

## 11. Risks & Open Questions

| # | Risk / question | Resolution / ADR |
|---|---|---|

## 12. References

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1.0 | YYYY-MM-DD | Initial draft |
````

### 6.2 Lifecycle

| From | Event | To | Guard |
|---|---|---|---|
| — | spec created | `Draft` | front-matter valid |
| `Draft` | review passed | `Approved` | §6 contracts complete; every §8 AC names a test path |
| `Approved` | all ACs green in CI | `Implemented` | every `AC-` id found under `tests/` |
| `Implemented` | replaced | `Superseded` | `superseded_by` names the successor |

Normative rules:

- **B-1** Implementation MUST NOT begin before a spec reaches `Approved`.
- **B-2** Tests MUST be written after `Approved` and before implementation.
- **B-3** A MAJOR version bump on a spec at `Approved` or later MUST be
  accompanied by an ADR recording why the contract changed.
- **B-4** A spec at `Implemented` MUST NOT have an `AC-` id absent from the test
  tree. `scripts/docs_check.py` fails the build on violation.
- **B-5** Specs MUST live in `docs/specs/`. Descriptive architecture prose MUST
  live in `docs/01-architecture/` and MUST open with a link to its governing
  spec.

### 6.3 Versioning

Semver on the `version` front-matter field:

- **MAJOR** — a contract in §6 is removed or retyped (breaking).
- **MINOR** — an additive field, a new AC, a new Behaviour.
- **PATCH** — prose only; no §6, §7, or §8 change.

`SPEC-00N` maps 1:1 to migration Phase N. Sub-specs take a letter suffix
(`SPEC-003a`). Specs are **never** renumbered.

### 6.4 Errors

`N/A` — this spec defines process, not runtime behaviour.

### 6.5 Configuration

`N/A` — no runtime settings.

## 7. Behaviour

- **B-6** Every architecture guide under `docs/01-architecture/` MUST begin with
  a blockquote naming its governing spec and version.
- **B-7** Mermaid source MUST NOT appear outside `docs/09-diagrams/`. Other
  documents link to a diagram; they never copy it. Copies diverge.
- **B-8** A pull request that changes a file under `src/` or `intelligence/`
  MUST also change `CHANGELOG.md`.
- **B-9** JSON Schema artefacts under `docs/specs/contracts/` MUST be
  regenerated whenever a model in `src/sephiroth/contracts/` changes.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-000-01 | Every file matching `docs/specs/SPEC-*.md` has front-matter with a legal `status` and a semver `version` | §6.2 | `scripts/docs_check.py` |
| AC-000-02 | Every `AC-\d{3}-\d{2}` id in a spec with `status: Implemented` appears at least once under `tests/` | B-4 | `scripts/docs_check.py` |
| AC-000-03 | No ` ```mermaid ` fenced block exists outside `docs/09-diagrams/` | B-7 | `scripts/docs_check.py` |
| AC-000-04 | Every key under `components.*` in `docs/project-state.yaml` resolves to a path that exists | §5 | `scripts/docs_check.py` |
| AC-000-05 | Regenerating JSON Schema from `sephiroth.contracts` equals the committed `docs/specs/contracts/*.schema.json` byte-for-byte | B-9 | `tests/test_contracts_schema.py` |
| AC-000-06 | Every `F-\d{3}` referenced in `docs/traceability.md` exists in `docs/03-features/feature-registry.md` | §5 | `scripts/docs_check.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Docs gate | front-matter, AC coverage, mermaid placement, project-state paths, feature refs | `scripts/docs_check.py`, CI job `docs` |
| Contract | JSON Schema drift | `tests/test_contracts_schema.py`, CI job `test` |

## 10. Migration & Compatibility

Shadows nothing — this spec introduces a process, not code. `docs/INTEGRATION_GUIDE.md`
is deleted in Phase 0 rather than migrated: it describes a structure that does
not exist, so there is nothing to preserve. Its only accurate content (the MCP
server walkthrough) moves to `docs/04-development/setup.md`.

## 11. Risks & Open Questions

| # | Risk / question | Resolution / ADR |
|---|---|---|
| 1 | SDD ceremony slows a solo thesis project to a crawl | Only phase-level specs are required (6 total), not per-PR specs. NG-2 exempts non-contract changes. |
| 2 | `docs_check.py` becomes a maintenance burden of its own | Capped at stdlib + PyYAML, ~120 lines, six checks. If it needs a dependency, the check is too clever — delete it. |
| 3 | Specs freeze contracts too early, before the design is understood | `Draft` status is explicitly cheap to revise; only `Approved` freezes. Phase 3 is split 3a/3b precisely so parity is proven before dynamism is specified. |

## 12. References

- `docs/00-migration-charter.md` — the migration's frozen external contracts and shim rules.
- Keep a Changelog 1.1.0 — `CHANGELOG.md` format.
- RFC 2119 — normative keywords.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-16 | Initial version; approved as the governing process spec |
