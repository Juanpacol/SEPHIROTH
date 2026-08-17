---
id: SPEC-008
title: Dynamic Capability-Matching Planner
phase: 5
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-08-19
updated: 2026-08-19
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-003]
adrs: []
features: [F-029]
diagrams: []
---

# SPEC-008 — Dynamic Capability-Matching Planner

## 1. Summary

Closes `SPEC-003` NG-1: `route_specialists_dynamic(context, client)` asks
the model which of the four specialist agents are relevant to a given
consultation, instead of the static key-presence heuristic
(`route_specialists`) checking `image_path`/`lab_results`/`medications`
directly. It is additive and feature-flagged
(`settings.enable_dynamic_planner`, default `False`) — the static planner
stays the only path the offline eval exercises, and the only fallback the
dynamic path degrades to on any failure.

## 2. Motivation

`route_specialists`'s four branches were flagged as a known simplification
since Phase 3 (`docs/specs/SPEC-003-agent-runtime.md` NG-1,
`docs/traceability.md` F-029): a specialist runs whenever its input key is
present, regardless of whether the *query* actually needs that specialty.
A patient with an `image_path` in context but a question purely about a
drug interaction still runs the radiology agent today — correct by the
letter of the heuristic, wasteful by intent. `H1` (unnecessary invocation
rate) cannot be measured at all while the only planner is a fixed
key-presence check with nothing to compare it against.

## 3. Goals

- **G-1** `route_specialists_dynamic(context, client) -> list[str]` calls
  `client.generate_json` with a schema constraining `agents` to the four
  known specialist node names, and returns that list when valid.
- **G-2** Any failure mode — a `generate_json` exception, a non-dict
  payload, a missing/empty/all-invalid `agents` list — degrades to
  `route_specialists(context)`, the static heuristic. Routing must never
  produce zero specialists because this function failed.
- **G-3** `settings.enable_dynamic_planner` (default `False`) gates which
  planner `run_consultation`/`stream_consultation` use; the frozen
  `routing` SSE event's *shape* (`{"event": "routing", "agents": [...]}`)
  is unchanged either way — only which names populate `agents` can differ.

## 4. Non-Goals

- **NG-1** Changing the static `route_specialists` function itself — it
  remains byte-identical to its Phase 3 relocation, still the parity gate
  `tests/test_workflow.py` checks by name.
- **NG-2** Running the dynamic path in the offline eval (`--mode ci`) — no
  live model exists there; the flag defaults off specifically so eval
  stays deterministic without special-casing it.
- **NG-3** Measuring `H1` (unnecessary invocation rate) — that requires
  live traffic with the flag on and a way to judge which specialists were
  actually "necessary," a research question this spec only makes
  answerable, not one it answers.
- **NG-4** Coordinator routing or a variable number of coordinator calls —
  the coordinator always runs; only which of the four specialists precede
  it can vary.

## 5. Definitions

- **Dynamic routing decision** — the validated `agents` list a
  `generate_json` call returns, after filtering to only known specialist
  node names and deduplicating.
- **Degrade** — return `route_specialists(context)`'s result instead of a
  dynamic decision, silently from the caller's perspective (no error
  surfaces; the consultation proceeds as if the flag were off for that one
  routing decision).

## 6. Contracts

### 6.1 Types

No contract types change. `_ROUTING_SCHEMA` (module-private in
`planner.py`) is a plain JSON Schema dict, not a `sephiroth.contracts`
type — it exists only to shape one `generate_json` call.

### 6.2 Interfaces

```python
# src/sephiroth/runtime/planner.py
async def route_specialists_dynamic(context: dict | None, client: ModelProvider) -> list[str]: ...
```

### 6.3 Settings

| Setting | Module | Default |
|---|---|---|
| `enable_dynamic_planner` | `platform/core/config.py` | `False` |

### 6.4 Wire contract

Unchanged. `{"event": "routing", "agents": [...]}` (`docs/00-migration-charter.md`
§2) — `agents` is still a list of the same four possible node-name strings
regardless of which planner produced it.

## 7. Behaviour

- **B-1** With the flag off (default), `_route` in `executor.py` calls the
  static `route_specialists` exactly as before this spec — zero code path
  difference for existing deployments.
- **B-2** With the flag on, `_route` awaits `route_specialists_dynamic`.
  Its result replaces `node_names` for both `run_consultation` and
  `stream_consultation` — the same variable every downstream line already
  used, so no other code needed to change.
- **B-3** An empty `agents` list from the model is treated as an *invalid*
  decision, not a valid "run nothing": it degrades to the static
  heuristic rather than returning an empty specialist set.
- **B-4** An unknown agent name in `agents` (anything outside the four
  known node names) is filtered out silently; if filtering empties the
  list, that also degrades to the static heuristic.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-008-01 | `route_specialists_dynamic` returns a valid model-chosen subset of the four node names for image/labs/medications signals | G-1 | `tests/test_dynamic_planner.py` |
| AC-008-02 | `route_specialists_dynamic` degrades to `route_specialists(context)` on a `generate_json` exception, a non-dict payload, a malformed/empty/all-unknown `agents` list | G-2, B-3, B-4 | `tests/test_dynamic_planner.py` |
| AC-008-03 | With `enable_dynamic_planner=True`, the `routing` SSE event and `run_consultation`'s `agent_outputs` reflect the dynamic decision, not the static one | G-3, B-2 | `tests/test_dynamic_planner.py` |
| AC-008-04 | With `enable_dynamic_planner=False` (default), `test_workflow.py`/`test_sse_contract.py`/`test_api_agents.py` pass unmodified — proof the change is additive (and, by extension, that the offline eval — `--mode ci`, which never sets the flag — is unaffected) | B-1, NG-2 | `tests/test_workflow.py`, `tests/test_sse_contract.py`, `tests/test_api_agents.py` (all pass unmodified) |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit — planner | Each of the 4 static-parity cases (image/labs/medications/degrade), plus non-dict/malformed/exception degradation, plus unknown-name filtering | `tests/test_dynamic_planner.py` |
| Integration | Flag wired through `run_consultation`/`stream_consultation`; `routing` event reflects the dynamic decision | `tests/test_dynamic_planner.py` |
| Frozen (unaffected) | Default-off path passes the existing parity/contract suite unmodified | `tests/test_workflow.py`, `tests/test_sse_contract.py`, `tests/test_api_agents.py` |

## 10. Migration & Compatibility

No shims — new code only (`route_specialists_dynamic` in the existing
`planner.py`; one new setting). No contract or wire-shape change; no
migration. Fully backward compatible by construction — the default value
of the new setting reproduces the pre-existing behaviour exactly.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | The dynamic planner has never been exercised against a live model — only a scripted `FakeLLMClient` | Documented (NG-2); real validation needs a `GEMINI_API_KEY` run this environment cannot provide, same limitation as every other threshold-tuning gap in this project |
| 2 | Prompt quality (which specialists the model actually picks) is untuned | Out of scope this cycle — the spec's job is a correct, safe degradation contract, not prompt engineering; revisit once H1 data exists |
| 3 | `_ROUTING_SCHEMA`'s enum hardcodes the 4 node names from `planner.SPECIALISTS`, duplicating `registry.SPECIALISTS`'s keys | Accepted duplication — `registry.SPECIALISTS` is keyed by the same 4 strings by construction; a 5th specialist added later needs both updated, same as today's `route_specialists`'s 4 branches |

## 12. References

- `docs/specs/SPEC-003-agent-runtime.md` (NG-1, the deferral this spec closes)
- `docs/traceability.md` (F-029, H1)
- `docs/00-migration-charter.md` §2 (the frozen `routing` event)

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved. |
