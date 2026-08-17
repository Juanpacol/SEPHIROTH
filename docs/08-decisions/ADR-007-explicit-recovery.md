# ADR-007 — Explicit, classified recovery

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** decided 0, not yet executed

> **Correction (2026-08-19):** this line originally read "executed 3." It
> wasn't — Phase 3 (Agent Runtime) relocated the executor but never built
> `src/sephiroth/runtime/recovery.py`; an agent raising still propagates
> uncaught today, exactly as it did before the migration. Tracked as an
> open gap in `docs/project-state.yaml` (`Recovery engine`), not assumed
> done. See `docs/03-features/feature-registry.md` F-032/F-033.

## Context

Recovery today exists at exactly one level: `FallbackLLMClient` catches
`LLMUnavailableError` and retries on the secondary provider. Everything else —
an agent raising, a tool timing out, a retrieval returning nothing — propagates.

## Decision

A recovery engine that **classifies** a failure, then selects an action:

```
failure → classify → RETRY | FALLBACK | REPLAN | ABSTAIN
```

Every failure carries a `FailureCategory`; every recovery action and its outcome
is recorded in the trace.

## Rationale

- **Classification is what makes recovery measurable.** "The system recovered
  73% of the time" is meaningless without knowing from *what*. The closed
  taxonomy lets failures aggregate by component, which is Chapter 8 of the thesis.
- **`REPLAN` is why this needs a runtime.** Retry and fallback are library
  concerns. Replanning — deciding the original approach was wrong and choosing a
  different one — requires a planner to go back to, and is the capability that
  distinguishes a runtime from a pipeline with error handling.
- **`ABSTAIN` is a legitimate terminal state.** Sometimes the right recovery is
  to stop, and say so.
- H4 requires this to exist before it can be tested at all.

## Consequences

Recovery can loop, so it needs bounds: `max_attempts` per step and
`max_iterations` per plan, both enforced at the type level in `ExecutionPlan`.

Recovery costs latency and tokens. H6 must report the cost of recovery
separately from the cost of verification, or the two confound each other.

`succeeded: bool | None` on `RecoveryAction` distinguishes *not yet known* from
*attempted and failed* — a distinction that silently corrupts recovery success
rate if collapsed.

## Alternatives rejected

**Retry everything uniformly** — retrying a planning error just reproduces it,
burning quota to reach the same wrong answer.
**Let failures propagate** — the current behaviour; makes H4 unanswerable and
makes any tool outage a failed consultation.
