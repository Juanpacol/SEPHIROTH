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
| | F-036 claim extraction | `sephiroth/verification/` | 📋 | H3 | claim support rate | 📋 phase 4 |
| | F-037 five-state verification | `sephiroth/verification/` | 📋 | H3 | unsupported claim rate | 📋 phase 4 |
| **R-002** Decline rather than answer unsafely | F-040 abstention engine | `sephiroth/safety/` | 📋 | H3 | abstention rate **and** precision | 📋 phase 4 |
| | F-041 output safety engine | `sephiroth/safety/` | 📋 | — | unsafe answer rate | 📋 phase 4 |
| | F-038 conflict detection | `sephiroth/verification/` | 📋 | — | contradiction detection rate | 📋 phase 4 |
| **R-003** Provider-independent | F-022 `ModelProvider` interface | `sephiroth/models/` | `test_model_provider_protocol.py` | H5 | all metrics, per provider | ✅ implemented; H5 experiment not yet run |
| | F-023 config-driven selection | `sephiroth/models/factory.py` | `test_llm_factory.py` | H5 | — | ✅ implemented |
| **R-004** Capability-based selection | F-026 agent registry | `sephiroth/runtime/registry.py` | 📋 | H1 | agent selection accuracy | 📋 phase 3 |
| | F-028 static planner (parity) | `sephiroth/runtime/planner.py` | 📋 `test_runtime_parity.py` | — | — | 📋 phase 3a |
| | F-029 dynamic planner | `sephiroth/runtime/planner.py` | 📋 | H1 | unnecessary invocation rate | 📋 phase 3b |
| | F-030 capability router | `sephiroth/runtime/router.py` | 📋 | H1 | tool selection accuracy | 📋 phase 3 |
| **R-005** Failures classified and handled | F-033 recovery engine | `sephiroth/runtime/recovery.py` | 📋 | H4 | recovery success rate | 📋 phase 3 |
| | F-032 lifecycle state machine | `sephiroth/runtime/` | 📋 | H4 | completion under fault injection | 📋 phase 3 |
| | F-025 tool timeout/retry/fallback | `sephiroth/tools/` | 📋 | H4 | tool success rate | 📋 phase 2 |
| **R-006** Replayable traces | F-042 execution traces | `sephiroth/telemetry/` | 📋 | H6 | latency, tokens, cost | 📋 phase 5 |
| | F-043 span redaction | `sephiroth/contracts/trace.py` | `test_contracts_models.py` | — | zero PHI in spans | 🚧 contract done |
| | F-020 domain contracts | `sephiroth/contracts/` | `test_contracts_schema.py` | — | — | ✅ implemented |
| **R-007** Tools confined to authorised agents | F-021 dispatch-time authorization | `intelligence/mcp/registry.py` | `test_tool_authorization.py` | — | policy violation rate | ✅ implemented |
| | F-024 tool capability metadata | `sephiroth/tools/` | 📋 | — | — | 📋 phase 2 |
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
| R-001 | Partially | Provenance checked today; claim-level content verification is phase 4 |
| R-002 | No | No abstention mechanism exists; this is the largest gap |
| R-003 | Partially | Formal interface closed in phase 1; the H5 cross-provider experiment itself hasn't run |
| R-004 | No | Routing is a static key-presence check |
| R-005 | Partially | LLM-level fallback only; no agent or tool recovery |
| R-006 | No | Contracts defined; nothing emits traces yet |
| R-007 | **Yes** | Closed in phase 0 |
| R-008 | **Yes** | Enforced continuously by the suite and the three gates |

Two of eight requirements are fully met, one (R-003) partially so as of Phase 1.
That is the honest starting point, and it is what the phases exist to change.
