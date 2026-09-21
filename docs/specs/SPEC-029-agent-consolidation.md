---
id: SPEC-029
title: Agent Consolidation
phase: 14
version: 0.1.0
status: Approved
authors: [jbotero]
created: 2026-09-21
updated: 2026-09-21
supersedes: [SPEC-008]
superseded_by: null
depends_on: [SPEC-000, SPEC-003, SPEC-007]
adrs: [ADR-016]
features: [F-026, F-029, F-032]
diagrams: []
---

# SPEC-029 — Agent Consolidation

## 1. Summary

Removes the `laboratory` and `coordinator` agents and the multi-agent
fan-out path they exist for, leaving exactly one consultation path:
`intent_router.route_intent` picks one of three specialists
(`radiology`, `drug_safety`, `evidence`), and that specialist's answer is
the final answer. Formally supersedes `SPEC-008` (the dynamic planner),
which only ever ran inside the fan-out this removes. Amends
`SPEC-003 §6.1`'s `AgentCapability` registry contract — see §10.

## 2. Motivation

`settings.enable_single_agent_mode` defaults `True`
(`platform/core/config.py:270`) and nothing outside tests sets it `False`.
That makes the entire multi-agent fan-out — `src/sephiroth/runtime/planner.py`
(117 lines), `src/sephiroth/runtime/router.py` (26 lines), the multi-agent
branches of `executor.py::_select_and_run`/`stream_consultation` (~55
lines), and the `COORDINATOR` capability itself (37 lines) — unreachable in
production. `settings.enable_dynamic_planner`
(`platform/core/config.py:259`, `SPEC-008`) only ever applies inside that
same unreachable path, so it inherits the same problem one level down.

Separately, `LABORATORY` (`src/sephiroth/runtime/registry.py:70-84`) is a
38-word prompt asking a small local LLM to do, by free-text reasoning over
raw lab values, exactly what `src/sephiroth/safety/risk.py`'s curated,
deterministic rules already do at read time in `patients.py::_summary`/
`_full` — with no test asserting `laboratory`'s own output is clinically
correct, only that it exists and is wired (`tests/test_agent_registry.py`).
An LLM agent duplicating a deterministic check adds a hallucination surface
with no capability gain.

Both findings came out of the 2026-09-20 agent-reliability audit that also
produced `SF056` (Fase 2 of the same plan) — this spec is Fase 3, the part
of that audit that changes a normative type in `SPEC-003 §6.1` and
therefore needs a spec + ADR per `SPEC-000` B-3, rather than landing as a
plain fix.

## 3. Goals

- **G-1** Exactly one consultation path: `intent_router` picks one
  specialist, that specialist answers. No dead branch behind a flag that
  defaults to skipping it.
- **G-2** Remove `laboratory` as an LLM agent without silently dropping lab
  interpretation — deterministic risk flags (`risk.py`) already surface it
  outside the chat path, and free-text lab questions fall through to
  `evidence` exactly as any other unmatched clinical question does today
  (`intent_router.DEFAULT_ROUTE`).
- **G-3** Every historical consultation's `explanation` (built on read,
  `sephiroth.telemetry.explain`) MUST keep rendering correctly for
  consultations that ran under the old multi-agent/laboratory paths —
  removing an agent identity must not retroactively degrade past data
  (`docs/00-migration-charter.md` §2.3).
- **G-4** Formally close `SPEC-008`: the dynamic planner it specifies has
  no path left to run once the fan-out is gone.

## 4. Non-Goals

- **NG-1** No change to `radiology`, `drug_safety`, or `evidence`'s own
  behavior, prompts, or tools — this spec only removes agents and the
  fan-out, it does not touch the three that remain (`SF056`/Fase 2 already
  covered their reliability fixes).
- **NG-2** No new capability-matching or planning logic. This is a
  reduction, not a redesign of `intent_router`'s three-tier routing
  (`SPEC-003`/`ADR-004`).
- **NG-3** No change to `citation_guard`, claim verification, or the
  abstention gate — they operate on whichever specialist's text they are
  given, unchanged.
- **NG-4** No change to `risk.py`'s deterministic lab rules themselves —
  this spec relies on them existing and being correct, it does not modify
  them.
- **NG-5** Does not re-litigate `ADR-004`'s rejection of "an LLM picks
  agents from a prompt list." Removing an unreachable fan-out is not
  adopting that rejected design — no code path in the result lets a model
  choose from an open-ended agent list; `intent_router`'s closed,
  three-tier selection is unchanged.

## 5. Definitions

- **Fan-out path** — the code reachable only when
  `settings.enable_single_agent_mode` is `False`: `planner.route_specialists`
  (and its dynamic sibling), `router.resolve`, `executor._route`, and
  `executor._run_coordinator`.
- **Single path** — `intent_router.route_intent` → one specialist →
  `_with_disclaimer` → verification/abstention. What remains after this spec.

## 6. Contracts

### 6.1 Types — amends `SPEC-003 §6.1`

Module: `src/sephiroth/runtime/registry.py`

`LABORATORY` and `COORDINATOR` are **removed**. `SPECIALISTS` and `AGENTS`
collapse into one dict — there is no longer a "specialists vs. all agents"
distinction once there is no coordinator to add on top:

```python
RADIOLOGY: AgentCapability
DRUG_SAFETY: AgentCapability
EVIDENCE: AgentCapability
AGENTS: dict[str, AgentCapability]  # the 3 intent_router selects from
```

`get_capability(node_name)` keeps its existing signature and `KeyError`
behavior (`SPEC-003 §6.1`) — `"laboratory"` and `"coordinator"` become
unknown names, which is already a defined, tested failure mode.

Module: `src/sephiroth/contracts/capability.py` — no change; `model_hint`,
`require_tool_call`, etc. are all unaffected. `AgentCapability` as a type is
still exactly what `SPEC-003 §6.1` defines.

### 6.2 Interfaces

Module: `src/sephiroth/runtime/executor.py`

```python
async def run_consultation(client, query, patient_id="", context=None) -> dict: ...
async def stream_consultation(client, query, patient_id="", context=None) -> AsyncIterator[dict]: ...
```

Signatures unchanged (`SPEC-003 §6.2`). Internally, `_select_and_run` loses
its `if settings.enable_single_agent_mode` branch — the single-agent body
becomes the only body. `_route`, `_run_coordinator`, and the multi-agent
branch of `stream_consultation` are deleted, not degraded.

**Removed** modules: `src/sephiroth/runtime/planner.py`,
`src/sephiroth/runtime/router.py`.

### 6.3 State machine

`N/A` — no change to `LifecycleState` transitions; a run still goes
`SELECTED → EXECUTING → COMPLETED|FAILED` for exactly one agent instead of
N, which was already a legal trace shape (a specialist that failed its
retries and left the rest of a multi-agent run to continue).

### 6.4 Errors

`N/A` — no new exception types. `get_capability("laboratory")` /
`get_capability("coordinator")` now raise the pre-existing `KeyError` path
instead of returning a capability, which is the same failure mode
`SPEC-003 §6.1` already defines for any unknown name.

### 6.5 Configuration

Module: `platform/core/config.py`

| Field | Change |
|---|---|
| `enable_single_agent_mode` | **Removed.** The single path is unconditional; there is no longer a second mode to flag between. |
| `enable_dynamic_planner` | **Removed.** `SPEC-008`'s dynamic routing only ran inside the fan-out this spec removes. |

## 7. Behaviour

- **B-1** `route_intent` MUST select only from `{radiology, drug_safety,
  evidence}`. `laboratory` MUST NOT appear as a routable node name anywhere
  in `intent_router.py` (keyword tier, context-signal tier, or the LLM
  classification schema's enum).
- **B-2** A free-text lab-interpretation question that previously matched
  `intent_router`'s `laboratory` keyword rule or `has_lab_results` context
  signal MUST fall through to the next tier and, absent any other match,
  resolve to `evidence` (`DEFAULT_ROUTE`) — never raise, never resolve to a
  removed agent.
- **B-3** `sephiroth.telemetry.explain._NO_TOOL_ACTIONS` MUST keep its
  `"laboratory"` and `"coordinator"` entries after this phase, even though
  no live consultation can produce those agent names going forward —
  removing them would degrade `explanation` for every consultation
  persisted before this phase (charter §2.3).
- **B-4** `RunState.coordinator_result` and the wire-shape support for a
  `coordinator` entry in a persisted `agents` list MUST remain readable —
  this spec removes the capability that *produces* new coordinator data,
  not the ability to *render* old data that already has it.
- **B-5** No module under `src/`, `intelligence/`, or `platform/` may
  import `sephiroth.runtime.planner` or `sephiroth.runtime.router` after
  this phase (mirrors `SPEC-003` B-5's langgraph-import check pattern).

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-029-01 | `sephiroth.runtime.registry.AGENTS` contains exactly `{radiology, drug_safety, evidence}` | §6.1 | `tests/test_agent_registry.py` |
| AC-029-02 | `get_capability("laboratory")` and `get_capability("coordinator")` raise `KeyError` | §6.4 | `tests/test_agent_registry.py` |
| AC-029-03 | `platform.core.config.Settings` has no `enable_single_agent_mode` / `enable_dynamic_planner` field | §6.5 | `tests/test_config_flags.py` |
| AC-029-04 | `import sephiroth.runtime.planner` and `import sephiroth.runtime.router` both raise `ModuleNotFoundError` | B-5 | `tests/test_no_fanout_modules.py` |
| AC-029-05 | A query that matches the old `laboratory` keyword rule (e.g. "interpret this elevated potassium") routes to `evidence`, not an error | B-1, B-2 | `tests/test_intent_router.py` |
| AC-029-06 | `build_explanation` given a persisted `agents` list containing `"laboratory"` or `"coordinator"` (simulating pre-migration data) still renders a non-generic step for each | B-3 | `tests/test_explainability.py` |
| AC-029-07 | `run_consultation`/`stream_consultation` always take the single-specialist path — no code path reachable that runs more than one specialist per consultation | G-1 | `tests/test_runtime_executor.py`, `tests/test_workflow.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Registry | Agent set, `KeyError` on removed names | `tests/test_agent_registry.py` |
| Routing | Laboratory-shaped queries degrade to `evidence`, not an error | `tests/test_intent_router.py` |
| Config | Removed flags actually gone, no dangling reads | `tests/test_config_flags.py` (new) |
| Dependency hygiene | No import of the deleted fan-out modules | `tests/test_no_fanout_modules.py` (new) |
| Explainability | Historical `laboratory`/`coordinator` steps still render | `tests/test_explainability.py` |
| Characterization | Full consultation, single path only, existing SSE/persistence shape unchanged | `tests/test_workflow.py`, `tests/test_sse_contract.py`, `tests/test_api_agents.py` |

## 10. Migration & Compatibility

**Amends, does not replace, `SPEC-003`.** `SPEC-003` remains the governing
spec for `Agent`, the executor's single-specialist path, and the frozen SSE
contracts; only its §6.1 registry contract (the specific set of
`AgentCapability` records) changes. `SPEC-003`'s own front-matter/changelog
gets a `2.0.0` entry once this spec reaches `Implemented`, cross-referencing
this document — not before, per `SPEC-000` B-1 (no contract is live until
approved and implemented).

**Fully supersedes `SPEC-008`.** The dynamic planner it specifies
(`route_specialists_dynamic`, `enable_dynamic_planner`) has no path left to
run once the fan-out is removed; `SPEC-008`'s `status` moves to
`Superseded` in the same PR that deletes `planner.py`.

**Strangler-fig schedule (`ADR-010`):** per the plan (`SF058`/`SF059`/
`SF060` — tests-first, then implementation, per `SPEC-000` B-2), the deleted
modules do not get re-export shims: `ADR-010`'s shim rule exists to protect
external/legacy import surfaces during the runtime-extraction migration;
`planner.py`/`router.py` have exactly one internal caller
(`executor.py`), confirmed by grep, so a shim here would protect nothing
and just delay `SPEC-003 B-5`'s dependency-hygiene guarantee by a phase for
no reason.

**Explainability data, not code, is what must survive** (G-3/B-3): the
`_NO_TOOL_ACTIONS` template dict keeps its two entries permanently, the same
pattern `SPEC-003 §10` already used for shim modules — a small, explicitly
justified piece of "dead" code kept alive because deleting it breaks reading
old data, not because it still runs.

## 11. Risks & Open Questions

| # | Risk / question | Resolution / ADR |
|---|---|---|
| 1 | A clinician question needing genuine cross-referencing of a lab value against a drug or an image (the actual reason a coordinator merge existed) gets a narrower answer from one specialist instead of a synthesized one | Accepted per `ADR-016`: unmeasured in production (the fan-out was unreachable), and `intent_router`'s single-specialist answer already carries the full `CLINICIAN_VOICE`/citation discipline: the coordinator's compounding-hallucination risk (a fourth model call reasoning about text is itself already a synthesis) was a bigger cost than the diversity of view was worth on a local model. |
| 2 | Removing `laboratory` regresses lab-question quality specifically, vs. some other topic | Mitigated by G-2: the deterministic curated rules already run outside chat (`risk.py`), and free-text questions get `evidence`'s guideline-grounded answer instead of an LLM's free reasoning over raw numbers — arguably safer, not just cheaper. Not separately measured pre/post (no eval slice exists for this — a gap this spec does not close). |
| 3 | `RunState.coordinator_result` / `AgentResult` schema retains a field with no live producer forever | Accepted: removing it would be a second breaking change to `sephiroth.contracts` for a field that costs nothing to keep empty. Revisit only if `sephiroth.contracts` itself gets a major version bump for unrelated reasons. |

## 12. References

- [ADR-016](../08-decisions/ADR-016-remove-coordinator-and-laboratory.md)
- [ADR-004](../08-decisions/ADR-004-capability-based-routing.md) — why routing is closed-set capability matching, not open LLM choice (unaffected by this spec)
- [ADR-010](../08-decisions/ADR-010-runtime-separate-from-application.md) — strangler-fig shim policy
- `docs/specs/SPEC-003-agent-runtime.md` — the spec this amends
- `docs/specs/SPEC-008-dynamic-planner.md` — the spec this supersedes
- `docs/00-migration-charter.md` §2.3 — explanation-reconstruction guarantee

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-09-21 | Initial draft |
| 0.1.0 | 2026-09-21 | Approved — human review confirmed both design calls (`laboratory` deleted/delegated to `risk.py`; `coordinator`/multi-agent fan-out deleted entirely) before this spec was written |
