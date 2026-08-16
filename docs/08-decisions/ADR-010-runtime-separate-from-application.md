# ADR-010 — Separate the runtime from the clinical application

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** 0 (the framing decision)

## Context

The system was built as a clinical application that happens to contain agents.
Orchestration lives in `intelligence/agents/`, tools in `intelligence/mcp/`,
retrieval in `data/rag/` — all organised around the clinical domain, all
importable only in the context of this application.

## Problem

The research contribution is a claim about **agentic runtimes in general**:
that an explicit execution layer improves reliability over static orchestration.
A contribution that cannot be separated from one clinical app is a contribution
about that app.

There is also a concrete symptom: nothing in the codebase can be pointed at and
called "the runtime." The orchestration is a function that constructs a graph of
five named clinical classes.

## Decision

Extract a domain-agnostic runtime into `src/sephiroth/`, leaving the clinical
system as its **first consumer**. Nothing in the runtime names a clinical
concept; clinical specifics live in the agents and tools it is configured with.

Migrate strangler-fig, never rewrite: legacy modules become re-export shims,
deleted one phase after they are created.

## Rationale

- **It makes the contribution nameable.** After Phase 5, "the runtime" is a
  directory with a spec, not an argument.
- **It forces the abstraction to be real.** If `sephiroth/runtime/` cannot be
  written without importing something clinical, the separation has failed — and
  that failure surfaces as an import error rather than as a vague sense that the
  design is muddy. `tests/test_package_layout.py` already enforces the analogous
  rule for the contracts package.
- **The case study keeps working**, which is R-008. A rewrite would destroy the
  very evidence the thesis rests on: baseline C is the *existing artifact*, not
  a reconstruction of it.
- Editable install rather than a `pythonpath` entry, so `import sephiroth`
  resolves identically under pytest, uvicorn, `python -m` and Docker. Verified
  end-to-end in Phase 0.

## Consequences

Two package trees coexist for five phases, with shims and a deletion schedule to
manage. Coverage inflates while both exist and drops when shims go, so the
coverage gate is not raised mid-migration.

The discipline cost is real: every phase must resist the shortcut of importing
something clinical into the runtime.

## Alternatives rejected

**Keep one tree, reorganise internally** — cheaper, but the runtime never becomes
separable, and the contribution stays entangled with the case study.
**Big-bang rewrite on a long branch** — breaks CI for weeks, forfeits R-008, and
destroys the working baseline.
**Extract to a separate repository** — premature. The interfaces are still
moving, and a repository boundary would freeze them before they are understood.
