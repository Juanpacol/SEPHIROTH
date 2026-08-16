# SEPHIROTH — Migration Charter

**Version:** 1.0.0
**Status:** Active
**Governs:** architecture migration Phases 0–5

This document is the standing contract for the migration. It defines the
development loop, the strangler-fig rules, the external contracts that must not
break, and the phase dependency graph. Every phase spec (`docs/specs/SPEC-00N`)
operates inside these rules.

---

## 1. The development loop

Spec-Driven Development, per [SPEC-000](specs/SPEC-000-spec-process.md):

```
spec (Draft → Approved)  →  tests (failing)  →  implementation  →  spec (Implemented)
```

A phase is not started until its spec is `Approved`. A phase is not finished
until every `AC-` id in that spec is found in the test tree and green in CI.

---

## 2. Frozen external contracts

These four contracts are consumed outside the Python package boundary — by the
Next.js frontend, by the database, or by both. **Changing any of them requires a
coordinated frontend change in the same merge train.** They are locked by
`tests/test_sse_contract.py`, which is a permanent test and is never deleted.

### 2.1 SSE event stream

Wire framing is `data: {json}\n\n`. Five event types, emitted in this order:

| Event | Fields | Notes |
|---|---|---|
| `routing` | `agents: list[str]` | **node** names, underscore form (`drug_safety`) |
| `agent_completed` | `agent, summary, tool_calls` | `agent` is the **display** name, hyphen form (`drug-safety`); `summary` truncated to 280 chars; `tool_calls` entries carry `{name, arguments}` and **no `result`** |
| `final` | `answer, agents_involved, tool_calls, citation_report, explanation` | `tool_calls` entries here **do** carry `result` |
| `persisted` | `id` | emitted by the router after the stream, carries the consultation id |
| `error` | `detail` | router-level |

The underscore/hyphen split is real and load-bearing: the frontend normalises
with `name.replace("_", "-")` on `routing` and matches `agent_completed` against
both forms (`platform/frontend/app/copilot/page.tsx:262-341`).

**Unknown events are silently ignored by the frontend.** Therefore *adding* a
new event type is backward-compatible; changing any of these five is not.

### 2.2 Persistence shape

`platform/api/routers/agents.py::_persist` requires a final state shaped:

```python
{"final_answer": str, "agent_outputs": dict[str, str], "tool_calls": list[dict], "citation_report": dict}
```

`citation_report` MUST keep exactly the keys `{verified, fabricated, total_checked}`.
`citation_guard.audit()` requires the **full** tool_calls including `result` to
harvest allowed citations — this is why `agent_completed` strips `result` but
`final` does not.

### 2.3 `ConsultResponse`

`id, answer, agents_involved, tool_calls, citation_report, explanation, disclaimer`.

### 2.4 Derived explanation

`explanation` is **not persisted**. It is rebuilt on read, in two places —
`GET /api/agents/history` and the PDF export — via
`intelligence/agents/explainability.py::build_explanation`, which must stay a
pure function of `(agents_involved, tool_calls, citation_report)`.

Consequence: **any new agent identity needs an entry in `_ACTION_TEMPLATES` /
`_NO_TOOL_ACTIONS`**, or historical consultations degrade to generic step text
retroactively.

---

## 3. Strangler-fig rules

New code lands in `src/sephiroth/`. Legacy modules become re-export shims, then
are deleted one phase later.

1. **A shim re-exports names; it never re-implements.** No `try/except ImportError`,
   no conditional logic. If a shim contains an `if`, it is not a shim.
2. **Module-level globals must stay identical objects.** `tests/conftest.py::patch_llm_factory`
   does `monkeypatch.setattr(factory_module, "_client", fake)`. If the old module
   becomes `from new.module import *`, patching the old path binds a *copy* while
   the real global is read elsewhere — tests would pass while exercising nothing.
   Any shim over a module with mutable global state MUST retarget its test
   fixtures in the same pull request and MUST ship an identity test.
3. **A shim is deleted in the phase after the one that created it**, never at the
   end of the migration. A shim that survives two phases becomes permanent.
4. **Shims are listed in `[tool.coverage.report] omit`** — three-line re-exports
   would otherwise inflate the numerator while hiding real gaps.

### Shim schedule

| Shim | Created | Deleted |
|---|---|---|
| `intelligence/llm/*` | Phase 1 | Phase 2 |
| `intelligence/mcp/registry.py` | Phase 2 | Phase 3 |
| `intelligence/agents/{base,workflow}.py` | Phase 3a | Phase 3b |
| `intelligence/agents/{citation_guard,explainability,risk_engine}.py` | Phase 4 | Phase 5 |

---

## 4. Package layout and importability

`pythonpath = [".", "platform"]` in `pyproject.toml` serves pytest only. It does
**not** cover `uvicorn`, `python -m intelligence.evaluation.run` (the blocking
CI eval job), `scripts/smoke_test.sh`, or the Docker image.

Therefore `src/sephiroth/` is made importable by **editable install**
(`pip install -e .`), not by extending `pythonpath`. `[tool.setuptools]` uses
explicit `packages.find.where = ["src"]` — never autodiscovery, which would try
to package `intelligence/`, `data/`, and `platform/` as well.

The legacy roots keep working unchanged: `pythonpath` is not modified.

---

## 5. Coverage gate

`fail_under = 87` is computed over the union of `coverage.run.source`. Two
failure modes exist, and the dangerous one is silent:

- **Forgetting to add a new directory** → new code is invisible to the gate,
  CI passes, the migration is unverified.
- Adding the directory before its tests → CI red. Loud, therefore harmless.

**Rule:** every pull request that creates `src/sephiroth/<pkg>/` adds
`"src/sephiroth/<pkg>"` to `coverage.run.source` in that same pull request,
together with its tests. Never add `"src/sephiroth"` wholesale — a wildcard root
silently absorbs future subpackages and reintroduces the silent failure.

`tests/test_coverage_config.py` enforces this mechanically.

**`fail_under` is not raised during the migration.** While old and new code
coexist, coverage inflates; it drops when shims are deleted. The ratchet happens
once, at the end of Phase 5.

---

## 6. Test conventions

- The 32 legacy test modules stay flat in `tests/` and are **not moved** — churn
  without benefit, and it risks the coverage gate.
- New tests go under `tests/sephiroth/<pkg>/`. Because there is no
  `tests/__init__.py`, pytest collects by rootdir, so **basenames must be
  globally unique** across the whole test tree.
- Markers `spec`, `contract`, `integration`, `legacy` are registered in
  `pyproject.toml`.
- Skips are module-level `pytestmark = pytest.mark.skipif(<infra reachable>)`,
  never keyed on environment variables.

### The `FakeLLMClient` script-key landmine

`tests/conftest.py::FakeLLMClient._script_for` selects the first script key that
is a **substring of the system prompt**. The two canonical keys are
`"clinical evidence specialist"` and `"coordinating physician-assistant"`.

If a role prompt is reworded, or the system-prompt assembly order changes, the
affected tests silently fall through to `default_script` **and still pass while
asserting nothing**. `tests/test_prompt_contract.py` guards this and must remain
green before any prompt is touched.

---

## 7. Phase dependency graph

```
Phase 0  Foundation + tool-authorization hotfix
   │
   ▼
Phase 1  ModelProvider ──────────────┐
   │                                 │  (unblocks agents and tools alike:
   ▼                                 │   every agent takes `client` as its
Phase 2  Tool Runtime                │   only constructor argument)
   │                                 │
   ▼                                 ▼
Phase 3  Agent Runtime   3a parity → 3b dynamic
   │
   ├──▶ Phase 4a  Context Engine
   └──▶ Phase 4b  Verification & Safety
              │
              ▼
        Phase 5  Observability + shim removal
```

Ordering rationale:

- **ModelProvider first** because it is the cheapest phase with the highest
  de-risking value — its interface is already empirically fixed by three
  implementations plus the test double.
- **Tool Runtime before Agent Runtime**, so the new executor is built against a
  scoped, authorised tool executor rather than inheriting the authorization hole
  and being changed twice.
- **Agent Runtime before Verification**, because verification can only become a
  pluggable post-processing pipeline once something owns final-state assembly.
  Today that owner is a coordinator node body, which Phase 3 replaces.
- **Observability last**, deliberately: instrumenting a moving target is waste.
  By Phase 5 the four seams are frozen and tracing is pure decoration.

---

## 8. Non-negotiable gates

Three checks must pass in every phase, with no exceptions:

1. **`tests/test_sse_contract.py`** — the wire. Byte-level.
2. **The `eval` CI job** — the semantics. Unit tests catch shape drift; only the
   evaluation harness catches "the agents got dumber."
3. **`docker-build-smoke-test`** — the real import graph, which pytest's
   `pythonpath` hides.

## 9. Two-commit pattern

Two changes in this migration alter runtime behaviour in ways unit tests cannot
fully predict. Both ship in two commits: **permissive first** (log what would
have been blocked, change nothing), inspect the `eval` job output, then
**enforcing**.

- Phase 0 — tool authorization enforcement.
- Phase 4a — per-agent context views.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-16 | Initial charter, Phase 0 |
