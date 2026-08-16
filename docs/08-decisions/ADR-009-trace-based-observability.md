# ADR-009 — Trace-based observability

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** decided 0, executed 5

## Context

Observability today is `logger.info` lines: a request id in middleware, per-call
duration in the LLM clients, rate-limit warnings. The explainability module
renders a template-based audit trail from persisted tool calls.

## Problem

Nearly every metric in [methodology.md](../07-research/methodology.md) —
unnecessary invocation rate, recovery success rate, tokens per query, p95
latency, claim support rate — is a property of *one execution*. Log lines cannot
be aggregated into those without parsing prose.

**The trace is not a debugging aid. It is the measurement instrument.**

## Decision

Every run emits a structured `ExecutionTrace`: nested spans over four frozen
seams (`ModelProvider.chat`, `ToolScope.execute`, `Executor.step`,
`Verifier.check`), carrying plan, agent calls, tool calls, evidence, claims,
verification, safety, retries, latency, tokens, cost, and **model versions**.

Persisted as one nullable JSON column plus four indexed scalars (`trace_id`,
`risk_level`, `abstained`, `supported_claim_ratio`).

## Rationale

- Metrics come from replaying traces, not from instrumenting one-off runs — so
  a new metric can be computed against past runs without re-running them.
- **Model versions travel with the trace**, so a run against a different provider
  is never mistaken for a repeat of the same experiment. H5 depends on this.
- Four seams, not everywhere: they are already the natural chokepoints, and they
  have been deliberately frozen since Phase 1.
- Instrumentation is last precisely because instrumenting a moving target is
  waste.

## Redaction is a contract, not a convention

Span attributes are an **allow-list** (`agent`, `tool_name`, `model`, `rounds`,
token counts, `step_id`, `attempt`, `ok`, `status`). Anything else raises at
construction.

An allow-list fails closed; a deny-list would let the next field through by
default, and in this domain the next field is patient data. This is enforced in
`sephiroth/contracts/trace.py` today, before anything emits a span.

## Consequences

Instrumentation overhead is real and is itself measured (H6): a run with tracing
disabled must produce an identical `RunState` to one with it enabled.

JSON blob plus four scalars, not normalised tables — at thesis scale that is the
right trade, and it keeps the trace immutable and replayable. Revisit only if
dashboard queries force it.

## Alternatives rejected

**OpenTelemetry directly** — a fine backend, but the emitter is kept behind a
Protocol so telemetry is swappable; a model-agnostic runtime should not be
telemetry-vendor-locked either. OTel remains available as an emitter.
**Keep structured logs and parse them** — fragile, and loses nesting, which is
what makes "which agent caused this latency?" answerable.
