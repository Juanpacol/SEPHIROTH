# ADR-001 — Remove LangGraph in favour of a purpose-built executor

**Status:** Accepted
**Date:** 2026-08-16 (decided); revised 2026-08-19 (removal timing, see Migration)
**Phase:** decided in 0, executed in 3
**Supersedes:** the assumption in `SEPHIROTH_Transformation_Plan.md` §15 that this
ADR would be titled "Why LangGraph?"

## Context

`intelligence/agents/workflow.py` orchestrates five agents with LangGraph: a
conditional fan-out from `START` into up to four specialists, then a static
fan-in to a coordinator. It works, it is tested, and it has been in production
use.

The transformation plan assumed LangGraph would stay and that an ADR would
record *why it was chosen*. Auditing the code before writing that ADR inverted
the conclusion.

## Problem

SEPHIROTH's central capability is **dynamic planning**: a planner decides at
runtime which agents run, in what order, with what dependencies, and whether to
replan after a failure. LangGraph's fan-out is expressed as:

```python
graph.add_conditional_edges(
    START,
    lambda state: route_specialists(state.get("context")),
    list(SPECIALISTS),  # <- destination set, fixed at compile time
)
```

The set of possible destinations must be enumerated when the graph is compiled.
A runtime-decided node set cannot be expressed this way.

## Options considered

**A. Keep LangGraph, recompile the graph per request from the plan.**
Turns every consultation into a graph-construction step. That is a hand-rolled
scheduler wearing a LangGraph costume, plus per-request compile cost.

**B. Keep LangGraph, collapse to one `executor` node with a self-loop.**
The graph becomes a single node. LangGraph then contributes a `TypedDict` and an
import, nothing more.

**C. Keep LangGraph for its checkpointing and durability.**
Would be compelling — except `build_workflow()` calls `.compile()` with **no
checkpointer**. None of that value is currently realised, and `RunState` is a
plain serializable Pydantic model, so adding a checkpointer later is a Protocol
plus a table rather than a framework re-adoption.

**D. Replace it with a purpose-built executor.**

## Decision

**D.** Remove `langgraph` in Phase 3, in the same commit that replaces the
executor — not a phase later, as originally planned below. See the
**Migration** section's revision note.

## Rationale

1. **We use roughly 5% of it.** No checkpointer, no interrupts, no time travel,
   no resumable threads. What is actually used is fan-out/fan-in scheduling and
   two `operator` reducers.
2. **The shape is wrong for the target.** See above: compile-time destination
   enumeration is precisely what a dynamic planner cannot satisfy.
3. **The reducers are ten lines.** `operator.or_` on a dict and `operator.add`
   on a list become a `merge()` function — and, importantly, one that is
   *testable in isolation*. Today the merge exists only as an `Annotated`
   marker, so there is no way to unit-test that concurrent branches combine
   deterministically. Merge order is observable on the wire, so it deserves a
   test.
4. **No warm-graph optimisation is lost.** The graph is rebuilt and all five
   agents re-instantiated on every consultation already.
5. **Coupling.** A model-agnostic runtime whose scheduler is a hard dependency
   on one LLM ecosystem's framework is exactly the coupling SEPHIROTH exists to
   remove. Dropping it also shrinks the image and the dependency-audit surface.

The replacement is an `asyncio.gather` fan-out with bounded concurrency, a
deterministic merge, and a step budget — around 150 lines, which is *less* code
than the adapters option A or B would require.

## Consequences

**Positive.** Dynamic planning becomes expressible. The merge becomes testable.
One fewer large transitive dependency tree. The executor's behaviour is fully
ours to specify in SPEC-003.

**Negative.** We give up a well-tested scheduler for one we must test
ourselves — mitigated by `tests/test_workflow.py`, `test_sse_contract.py`, and
`test_api_agents.py`, which exercise the new executor through the exact same
public API, scripted client, and assertions as before, unmodified. Passing
unmodified **is** the parity proof; no separate side-by-side comparison
harness against the old graph was built (see Migration, below — the old graph
was not kept alive for one). We also give up LangGraph's ecosystem (LangSmith
tracing, Studio); Phase 5 builds tracing on our own `ExecutionTrace` instead,
which we need anyway for reproducible evaluation.

**Risk accepted.** If durable, resumable execution becomes a requirement, we
implement a checkpointer against `RunState`. This is a real cost, consciously
deferred, and cheap because state is serializable by construction.

## Alternatives rejected

Options A and B are rejected as complexity without benefit — both keep the
dependency while removing everything that justified it. Option C is rejected on
the factual grounds that the durability benefit is not currently realised.

## Migration

**Revised during implementation (2026-08-19).** The plan below — keep
`langgraph` installed through a "3a" parity phase, remove it only in a later
"3b" — assumed the old graph would be kept alive alongside the new executor
for an explicit side-by-side comparison. It wasn't needed: `test_workflow.py`,
`test_sse_contract.py`, and `test_api_agents.py` already exercise the exact
same public API with the exact same scripted client and assertions the old
graph was tested against, so those tests passing unmodified against the new
executor **is** the parity proof — a separate comparison harness would
duplicate that proof, not strengthen it. Maintaining a second, unused
implementation "in case of rollback" is exactly the complexity without
measurable benefit `docs/00-project/scope.md` rules out; `git revert` is the
real rollback mechanism.

`langgraph>=0.2` was therefore removed from `requirements.txt` in the same
phase (Phase 3) that replaced the executor, not deferred to a "3b." Gated by
`tests/test_no_langgraph.py`, which asserts no module under `intelligence/`,
`platform/`, or `src/` imports it.

~~Original plan (superseded): `langgraph>=0.2` stays in `requirements.txt`
through Phase 3a, so a rollback of 3b can still install and run the old graph.
It is removed in the same pull request that deletes
`intelligence/agents/workflow.py`.~~
