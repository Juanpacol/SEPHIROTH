# ADR-004 — Capability-based routing

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** decided 0, executed 3

## Context

Routing today is eleven lines in `intelligence/agents/workflow.py`:

- evidence always runs
- radiology if `context["image_path"]`
- laboratory if `context["lab_results"]`
- drug_safety if `context["medications"]`

It works, and it is fast and predictable. It is also the entire routing logic.

## Problem

It cannot answer *"which agent can assess a medication interaction?"* — only
*"was a medications key present?"* Adding an agent means editing the router,
the graph, and the specialist tuple. Adding a *domain* means rewriting all three.

There is also an unmeasured inefficiency: the frontend only ever sends
`{conditions}`, so in practice the router almost always selects evidence alone.
Whether that is correct is currently unknowable.

## Decision

Agents declare capabilities as data (`AgentCapability.capabilities`). The
planner states which capabilities a task requires; the router matches, then
filters by risk and policy.

## Rationale

- **It makes H1 testable.** "Does dynamic routing reduce unnecessary
  invocations?" requires a routing decision that can differ from the static one.
  Key-presence checks cannot differ from themselves.
- **Agents become data.** A registry entry, not a class plus three edits.
- **Risk becomes a routing input.** A high-risk task can require a verifying
  agent; a key-presence check has no vocabulary for that.

## Consequences

Routing becomes a component that can be wrong, so it needs its own metric —
agent selection accuracy — and a benchmark that distinguishes good selection
from bad. That is a real cost the static router did not have.

Mitigated by phasing: Phase 3a's planner **reproduces `route_specialists`
exactly**, proven by parity tests, before Phase 3b introduces any dynamism. The
static behaviour survives as a fallback and as baseline C.

## Alternatives rejected

**LLM picks agents from a prompt list** — untestable, non-deterministic, and no
mechanism for risk or permission filtering.
**Keep static routing** — leaves RQ1 unanswerable, which forfeits a research
sub-question rather than answering it negatively.
