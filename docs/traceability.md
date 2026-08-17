# Traceability matrix

Connects each requirement to the thing that implements it, the test that proves
it, and the metric that measures it. Read left to right, it answers *"how do you
know?"* for any claim the thesis makes.

```
Requirement → Feature → Implementation → Test → Experiment → Metric → Result
```

Requirements are defined in [scope.md](00-project/scope.md); features in
[the feature registry](03-features/feature-registry.md); hypotheses in
[hypotheses.md](07-research/hypotheses.md).

## Matrix

| Requirement | Feature | Implementation | Test | Hypothesis | Metric | Status |
|---|---|---|---|---|---|---|
| **R-001** Claims traceable to evidence | F-003 citation guard | `intelligence/agents/citation_guard.py` | `test_citation_guard.py`, `_adversarial` | — | citation precision | ✅ implemented |
| | F-006 hybrid retrieval | `data/rag/` | `test_rag_pipeline.py` | H2 | Recall@k, MRR | ✅ implemented |
| | F-034 per-agent context views | `sephiroth/context/views.py` | `test_context_views.py` | — | — | ✅ implemented (phase 4a) |
| | F-035 reranking/memory/budgeting | `sephiroth/context/{rerank,memory,budget}.py` | `test_context_{rerank,memory,budget}.py` | H2 | Recall@k, MRR (reranked) | ✅ implemented (phase 4a); H2 experiment not yet run against reranked results specifically |
| | F-036 claim extraction | `sephiroth/verification/claims.py` | `test_verification_claims.py` | H3 | claim support rate | ✅ implemented (phase 4); H3 experiment not yet run |
| | F-037 five-state verification | `sephiroth/verification/verify.py` | `test_verification_verify.py` | H3 | unsupported claim rate | ✅ implemented (phase 4); H3 experiment not yet run |
| **R-002** Decline rather than answer unsafely | F-040 abstention engine | `sephiroth/safety/abstention.py` | `test_safety_abstention.py` | H3 | abstention rate **and** precision | ✅ implemented (phase 4); thresholds are placeholders (SPEC-004 NG-3), precision not yet measured |
| | F-041 output safety engine | `sephiroth/safety/output_safety.py` | `test_safety_output_safety.py` | — | unsafe answer rate | ⚠️ input prompt-injection heuristic only (phase 4); PHI/toxicity/jailbreak/HITL deferred (SPEC-004 NG-2) |
| | F-038 conflict detection | `sephiroth/verification/verify.py` | `test_verification_verify.py` | — | contradiction detection rate | ✅ implemented (phase 4) |
| **R-003** Provider-independent | F-022 `ModelProvider` interface | `sephiroth/models/` | `test_model_provider_protocol.py` | H5 | all metrics, per provider | ✅ implemented; H5 experiment not yet run |
| | F-023 config-driven selection | `sephiroth/models/factory.py` | `test_llm_factory.py` | H5 | — | ✅ implemented |
| **R-004** Capability-based selection | F-026 agent registry | `sephiroth/runtime/registry.py` | `test_agent_registry.py` | H1 | agent selection accuracy | ✅ implemented (phase 3); H1 experiment not yet run |
| | F-028 static planner (parity) | `sephiroth/runtime/planner.py` | `test_workflow.py` (unmodified parity gate) | — | — | ✅ implemented (phase 3) |
| | F-029 dynamic planner | `sephiroth/runtime/planner.py` | `test_dynamic_planner.py` | H1 | unnecessary invocation rate | ✅ implemented (phase 5, SPEC-008); feature-flagged (`enable_dynamic_planner`, default off), degrades to static on failure; H1 metric not yet run (needs live traffic) |
| | F-030 capability router | `sephiroth/runtime/router.py` | `test_agent_registry.py` | H1 | tool selection accuracy | ⚠️ static lookup only, not capability-matching (phase 3) |
| **R-005** Failures classified and handled | F-033 recovery engine | `sephiroth/runtime/recovery.py` | `test_runtime_recovery.py`, `test_runtime_executor.py` | H4 | recovery success rate | ✅ implemented (phase 5, SPEC-007); RETRY/ABSTAIN only — FALLBACK/REPLAN explicit non-goals; H4 metric not yet run (needs live traffic) |
| | F-032 lifecycle state machine | `sephiroth/runtime/executor.py` | `test_runtime_executor.py` | H4 | completion under fault injection | ✅ implemented (phase 5, SPEC-007) |
| | F-025 tool call timeout | `sephiroth/tools/runtime.py` | `test_tool_runtime.py` | H4 | tool success rate | ⚠️ timeout only; retry/fallback deferred |
| **R-006** Replayable traces | F-042 execution traces | `sephiroth/telemetry/` | `test_telemetry_build_trace.py` | H6 | latency, tokens, cost | ⚠️ implemented (phase 5); real span coverage limited to 2 of 4 seams (SPEC-006 NG-1), tokens/cost still placeholders (NG-2) |
| | F-043 span redaction | `sephiroth/contracts/trace.py`, `sephiroth/telemetry/span.py` | `test_contracts_models.py`, `test_telemetry_span.py` | — | zero PHI in spans | ✅ implemented (phase 5) — enforced both at `Span` construction and at `traced_span`'s filtering boundary |
| | F-020 domain contracts | `sephiroth/contracts/` | `test_contracts_schema.py` | — | — | ✅ implemented |
| **R-007** Tools confined to authorised agents | F-021 dispatch-time authorization | `sephiroth/tools/runtime.py` | `test_tool_authorization.py` | — | policy violation rate | ✅ implemented |
| | F-024 tool capability metadata | `sephiroth/tools/servers.py` | `test_tool_runtime.py` | — | — | ✅ implemented |
| **R-008** Application never breaks | F-001, F-014 existing behaviour | `intelligence/agents/workflow.py` | `test_sse_contract.py`, `test_workflow.py` | — | suite green | ✅ continuously |
| | F-009 evaluation regression gate | `intelligence/evaluation/` | `test_eval_cli.py` | — | eval job PASS | ✅ implemented |

## How to read the Status column

✅ implemented and tested · 🚧 partially built · 📋 planned, with its phase named.

The empty `Result` column from the canonical chain is deliberate: results belong
to the research effort (stages 6–10 in [the roadmap](00-project/roadmap.md)) and
are filled in `docs/07-research/results.md` when it exists. Writing them now
would be fabrication.

## What this matrix is for

Three uses, in order of how often they come up:

1. **Reviewing a change.** If a pull request touches an implementation cell, its
   test cell must be satisfied. `scripts/docs_check.py` verifies every `F-XXX`
   here exists in the registry.
2. **Finding gaps.** Any row where Implementation is filled and Test is empty is
   an untested requirement. There are currently none.
3. **Writing the thesis.** Each requirement becomes a claim, and the row is the
   evidence chain backing it. Chapter 7 is this table with the Result column
   populated.

## Coverage of requirements

| Requirement | Fully satisfied | Notes |
|---|---|---|
| R-001 | Yes | Citation guard (provenance) feeds a 5-state claim-content verifier (phase 4); the LLM judge's own accuracy is unmeasured (SPEC-004 risk 5) |
| R-002 | Yes | Abstention engine gates every consultation (phase 4); thresholds are placeholders pending tuning (SPEC-004 NG-3) |
| R-003 | Partially | Formal interface closed in phase 1; the H5 cross-provider experiment itself hasn't run |
| R-004 | Yes | Dynamic capability-matching planner implemented (phase 5, SPEC-008), feature-flagged and off by default; static heuristic remains the always-available fallback; H1 metric run pending live traffic |
| R-005 | Yes | Recovery engine + lifecycle state machine implemented (phase 5, SPEC-007); FALLBACK/REPLAN out of scope, H4 metric run pending live traffic |
| R-006 | Partially | Traces now emitted and persisted (phase 5); only 2 of 4 named seams have real spans, tokens/cost are placeholders |
| R-007 | **Yes** | Closed in phase 0 |
| R-008 | **Yes** | Enforced continuously by the suite and the three gates |

Two of eight requirements are fully met, one (R-003) partially so as of Phase 1.
That is the honest starting point, and it is what the phases exist to change.
