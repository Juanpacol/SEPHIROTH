# ADR-016 — Remove the coordinator/multi-agent fan-out and the laboratory agent

**Status:** Accepted · **Date:** 2026-09-21 · **Phase:** decided 14, executed pending (SPEC-029)

## Context

`settings.enable_single_agent_mode` (`platform/core/config.py:270`) has
defaulted `True` since `ADR`-less decision #24 in `CLAUDE.md`, and nothing
outside tests ever sets it `False`. Everything the multi-agent fan-out
exists for — `planner.py`, `router.py`, `executor.py`'s multi-agent
branches, and the `COORDINATOR` capability — has been unreachable in
production since that default landed: ~235 lines, live only under test.
`settings.enable_dynamic_planner` (`SPEC-008`) only ever applies one level
further inside that same unreachable path.

Separately, the 2026-09-20 agent-reliability audit (the same audit behind
`SF056`) found `LABORATORY` (`registry.py:70-84`) is a 38-word LLM prompt
re-deriving, by free-text reasoning over raw values, exactly what
`src/sephiroth/safety/risk.py`'s curated deterministic rules already
compute at read time for the patient summary — with no test asserting the
agent's own clinical output is correct.

## Problem

Two different kinds of waste, both costing the same thing — a hallucination
surface with no measured benefit:

1. **Dead breadth.** A router, a merge step, and a fifth agent record exist
   only to be skipped. They still have to be read, reasoned about, and kept
   passing in tests on every change to the modules they touch — cost paid
   for capability nobody exercises.
2. **Redundant depth.** `laboratory` asks a small local model to do a job a
   deterministic function already does correctly and cheaply, in the same
   codebase, one import away.

## Decision

Remove both, in the phase this ADR accompanies (`SPEC-029`):

- Delete `COORDINATOR`, `planner.py`, `router.py`, and the multi-agent
  branches of `executor.py`. `intent_router → one specialist → answer`
  becomes the only consultation path — not a default with a dead
  alternative, an only.
- Delete `LABORATORY`. Lab-value interpretation stays covered exactly the
  way `ADR-004`'s "unmatched question" doctrine already handles anything
  else the router can't confidently place: it falls through to `evidence`,
  which answers with guideline-grounded text and a citation rather than
  free reasoning over raw numbers. The deterministic risk flags
  (`risk.py`) keep surfacing in the patient summary, untouched, outside
  the chat path entirely.
- Formally supersede `SPEC-008` (the dynamic planner) — it has no path left
  to run once the fan-out it lived inside is gone.

## Rationale

- **Unreachable code is not a safety margin, it's a maintenance tax.** A
  branch nothing exercises in production still has to be kept green, still
  gets touched by unrelated refactors, and gives false confidence that
  "the system supports multi-agent synthesis" when what actually ships is
  always one specialist's answer.
- **A fourth model call reasoning over three other models' text is itself
  a synthesis step, with its own hallucination risk** (`ADR-006`'s whole
  premise: claims need verification precisely because free-text synthesis
  fabricates). Removing the coordinator doesn't just cut latency, it
  removes one more place an unverified claim could enter the answer before
  the citation guard ever sees it.
- **Deterministic beats probabilistic when both exist for the same
  question**, and here both already do: `risk.py` predates and outperforms
  `laboratory` at the one job `laboratory` had. Keeping the LLM version
  around "for symmetry with the other three specialists" is aesthetic, not
  functional.
- **This does not reopen the choice `ADR-004` rejected.** `ADR-004` rejected
  an LLM picking agents from an open-ended prompt list. `intent_router`'s
  closed, three-tier selection over a fixed `{radiology, drug_safety,
  evidence}` set is unchanged by this decision — the set just has three
  members instead of four, chosen the same way it always was.

## Consequences

- A clinical question that would have benefited from a genuine
  cross-specialty synthesis (e.g. "this lab value plus this med plus this
  image") now gets one specialist's narrower answer instead of a merged
  one. Accepted: unmeasured in production today (the path was unreachable),
  so there is no regression to a working baseline, only a foregone
  hypothetical one.
- `laboratory`-shaped free-text questions get `evidence`'s guideline-and-
  citation answer instead of a specialist reading the raw number. This is
  the same trade the router already makes for any topic it can't
  confidently place, applied consistently to one more case, not a new kind
  of degradation.
- `RunState.coordinator_result` and the `agents`/`explanation` wire shapes
  keep supporting a `"coordinator"`/`"laboratory"` value forever, for
  reading data persisted before this phase (`docs/00-migration-charter.md`
  §2.3) — removing that support would be a second, unrelated breaking
  change bundled into this one.
- `SPEC-008` moves to `Superseded`. Its acceptance criteria and tests are
  removed along with the code they verified, not kept green artificially.

## Alternatives rejected

**Keep the fan-out as an opt-in "advanced mode," documented as
unsupported** — the plan's own text considered this; it fixes none of the
maintenance cost (the code still exists, still gets touched, still needs
tests) for a capability with zero measured production use. Choosing
between "delete it" and "label the dead thing as intentionally dead" only
makes sense when there's a concrete plan to make it live again; there
isn't one here.

**Give `laboratory` a real MCP tool instead of deleting it** (wrap
`risk.py` as a tool the agent calls) — considered and rejected: it would
recreate a second entry point to the exact same deterministic logic
`patients.py` already surfaces, for a chat surface that adds latency and a
new place for the LLM to misreport what the tool returned, with no
capability `evidence`'s existing fallback doesn't already cover for the
free-text case.

**Keep `enable_dynamic_planner`/`SPEC-008` alive independent of the
fan-out**, in case dynamic routing is wanted again later without a
coordinator — rejected: `route_specialists_dynamic` selects *which
specialists to fan out to*, a question that stops existing once there is
exactly one specialist per consultation. Reviving multi-specialist routing
later is a new spec on its own terms, not a reason to keep this one on
life support now.
