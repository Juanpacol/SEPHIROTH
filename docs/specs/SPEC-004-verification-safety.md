---
id: SPEC-004
title: Verification & Safety
phase: 4
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-08-19
updated: 2026-08-19
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-001, SPEC-002, SPEC-003]
adrs: [ADR-006, ADR-008]
features: [F-036, F-037, F-038, F-039, F-040, F-041]
diagrams: [D1]
---

# SPEC-004 — Verification & Safety

## 1. Summary

Adds claim-level content verification (`src/sephiroth/verification/`) and an
abstention gate (`src/sephiroth/safety/`) to the executor, replacing the
implicit assumption that every coordinator answer should reach the user.
`citation_guard` (provenance-only, binary) becomes a fast pre-filter feeding
a five-state, content-level verifier (ADR-006); its output drives a
deterministic confidence score and a typed `answer`/`partial`/`abstain`
decision (ADR-008). This phase also ends the `RunState` adoption deferral
from `SPEC-003` §10 — the executor's internal state is now the real
Pydantic contract, not a plain dict, now that it actually accumulates
evidence/claims/safety data. Context Engine (Phase 4a: reranking, memory,
compression, token budgeting) is explicitly out of scope — see `ADR-001`'s
sibling phase split in `docs/00-migration-charter.md` §7.

## 2. Motivation

`intelligence/agents/citation_guard.py` proves a citation string was really
returned by a tool; it never checks whether the sentence attached to that
citation says what the source says. A plausible sentence carrying a genuine
citation is more dangerous than a fabricated one, because it survives
inspection (ADR-006). Separately, nothing in the runtime can decline to
answer — `citation_guard.sanitize()` strips a fabricated citation and returns
the answer anyway regardless of how little of it is actually supported
(ADR-008). Both gaps are named explicitly in `docs/06-security/safety.md` as
the largest gaps in the system, and both contracts they need
(`VerificationStatus`, `Claim`, `VerificationReport`, `AbstentionDecision`)
have existed, validated, since Phase 0 — unused until now.

## 3. Goals

- **G-1** Decompose a coordinator answer into independently verifiable
  `Claim`s and classify each against retrieved evidence content, using the
  5-state `VerificationStatus` vocabulary.
- **G-2** Detect contradictions between claims.
- **G-3** Compute a deterministic confidence score from already-available
  signals (never LLM self-reported, per ADR-008).
- **G-4** Gate every consultation through an `AbstentionDecision`
  (`answer`/`partial`/`abstain`), with `has_unsupported_high_risk_claim`
  overriding any confidence threshold.
- **G-5** A minimal input-facing safety check (prompt-injection heuristic)
  wired into the same abstention gate as `policy_restriction`.
- **G-6** Adopt `sephiroth.contracts.RunState` as the executor's real
  internal state (ending the `SPEC-003` §10 deferral).
- **G-7** Preserve the frozen SSE/persistence contracts exactly — new fields
  are additive only.

## 4. Non-Goals

- **NG-1** Context Engine (reranking, memory, compression, token budgeting)
  — Phase 4a, a separate spec.
- **NG-2** PHI redaction of clinical text, output-side toxicity/jailbreak
  classifiers, rate limiting. The product exists to show a clinician their
  own patient's clinical content back to them — redacting it would break the
  product, and this is the same trade-off already documented in `CLAUDE.md`'s
  privacy notice. Deferred to a future spec once real telemetry shows they're
  needed.
- **NG-3** A tuning methodology for confidence weights / abstention
  thresholds. Values in §6.5 are explicit placeholders (ADR-008: "tuning
  them is itself an experiment"), not derived from data yet.
- **NG-4** `intelligence/agents/citation_guard.py` is not rewritten — it
  becomes a pre-filter feeding the new verifier (ADR-006), unchanged in
  behavior, and is *not* deleted this phase (see §10).
- **NG-5** Deleting `intelligence/mcp/registry.py` — that was `DEBT-009`,
  already closed in a prior, isolated cycle before this phase began.
- **NG-6** Reconciling `intelligence/evaluation/faithfulness.py::judge_llm`
  (an existing, offline-only, binary per-sentence eval metric) with the new
  live-path `sephiroth.verification` module. They now overlap conceptually;
  unifying them is left for a future phase once eval data shows whether the
  offline metric should be replaced or kept as an independent check.

## 5. Definitions

- **Claim** — one independently verifiable assertion extracted from an
  answer (`sephiroth.contracts.claims.Claim`).
- **Verdict** — a claim's `VerificationStatus` after judging it against
  evidence: `supported`, `partially_supported`, `unsupported`,
  `contradicted`, `unknown`.
- **Abstention** — the runtime's `answer`/`partial`/`abstain` decision for
  one consultation (`sephiroth.contracts.safety.AbstentionDecision`).

## 6. Contracts

### 6.1 Types

No contract types change shape. This phase *populates* Phase 0 contracts
that were previously unused at runtime: `Claim`, `Contradiction`,
`VerificationReport`, `EvidenceRecord`, `SafetyFlag`, `AbstentionDecision`,
and — for the first time — `RunState`/`ToolCall`/`AgentResult` as the
executor's actual internal state (not a plain dict).

### 6.2 Interfaces

Module: `src/sephiroth/verification/`

```python
async def extract_claims(answer: str, client: ModelProvider) -> list[Claim]: ...
def harvest_evidence(tool_calls: list[ToolCall]) -> list[EvidenceRecord]: ...
async def verify_claims(
    claims: list[Claim], evidence: list[EvidenceRecord], client: ModelProvider
) -> VerificationReport: ...
def compute_confidence(
    report: VerificationReport, citation_report: CitationReport, tool_failures: int
) -> float: ...
```

Module: `src/sephiroth/safety/`

```python
def decide(
    report: VerificationReport, confidence: float, input_flags: list[SafetyFlag]
) -> AbstentionDecision: ...
def check_input(query: str) -> list[SafetyFlag]: ...
```

Module: `src/sephiroth/runtime/executor.py` (unchanged public signatures)

```python
async def run_consultation(client, query, patient_id="", context=None) -> dict: ...
async def stream_consultation(client, query, patient_id="", context=None) -> AsyncIterator[dict]: ...
```

Both now return two additional, additive keys: `verification_report` and
`abstention`.

### 6.3 State machine

`N/A` — no new lifecycle states this phase. `RunState.lifecycle` remains
unpopulated (tracked as a pre-existing gap, `docs/project-state.yaml`, not
introduced or closed here).

### 6.4 Errors

`extract_claims`/`verify_claims` degrade gracefully on any `generate_json`
failure or malformed payload: an extraction failure yields no claims
(`supported_claim_ratio` stays `1.0`, matching "nothing was asserted"); a
verification failure yields every claim `UNKNOWN` (never silently
`SUPPORTED`). Neither ever raises past the executor — verification/safety
degrading to "answer normally" is intentional (fails open on the
*verification* layer, since claim-level checking is additive safety on top
of the pre-existing citation-guard pass, not the only safety net), while the
`has_unsupported_high_risk_claim`/contradiction/injection gates still fail
*closed* whenever they do have signal.

### 6.5 Configuration

New tunables (module-level constants, not settings — no runtime
reconfiguration exists for these yet, matching "simplest that satisfies the
spec"):

| Constant | Module | Value | Status |
|---|---|---|---|
| `FABRICATION_WEIGHT` | `verification/confidence.py` | 0.5 | tunable (ADR-008) |
| `TOOL_FAILURE_WEIGHT` | `verification/confidence.py` | 0.2 | tunable |
| `TOOL_FAILURE_CAP` | `verification/confidence.py` | 3 | tunable |
| `ABSTAIN_THRESHOLD` | `safety/abstention.py` | 0.4 | tunable |
| `PARTIAL_THRESHOLD` | `safety/abstention.py` | 0.65 | tunable |

## 7. Behaviour

- **B-1** The five frozen SSE events keep identical shape/casing (unchanged
  from Phase 3); `final` gains `verification_report`/`abstention` as
  additive optional keys.
- **B-2** `has_unsupported_high_risk_claim` overrides any confidence
  threshold — an answer that "looks confident" but asserts one unsupported
  high-risk claim must still abstain (`docs/06-security/safety.md`'s stated
  invariant).
- **B-3** Priority order in `safety.abstention.decide`: policy restriction >
  unsupported high-risk claim > contradiction > confidence thresholds. Each
  earlier check overrides a later, more lenient one.
- **B-4** `status == abstain` replaces `final_answer` entirely with a
  reason-templated decline message — never surfaces a possibly-fabricated
  answer alongside a decline.
- **B-5** `status == partial` keeps the coordinator's (citation-sanitized)
  answer, prefixed with a fixed caveat banner.
- **B-6** `verify_claims` makes exactly one batched `generate_json` call per
  consultation (not one per claim), per ADR-006's cost concern.
- **B-7** A judge verdict of `supported` is downgraded to
  `partially_supported` when the claim and its cited evidence share fewer
  than 2 overlapping tokens — the judge is never the sole evidence for a
  claim (ADR-006's stated mitigation).
- **B-8** `ToolCall.tool` (the contract's field name) is projected to the
  wire's `name` at exactly one point (`_tool_call_wire`) — no other code
  path performs this translation.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-004-01 | `extract_claims` returns `[]` on empty input, on a `generate_json` failure, and on a non-dict payload | §6.4 | `tests/test_verification_claims.py` |
| AC-004-02 | `verify_claims([], ...)` returns an empty report; `verify_claims(claims, [], ...)` marks every claim `UNKNOWN` | B-7, §6.4 | `tests/test_verification_verify.py` |
| AC-004-03 | A `supported` verdict with <2 overlapping tokens against its cited evidence is downgraded to `partially_supported` | B-7 | `tests/test_verification_verify.py` |
| AC-004-04 | `compute_confidence` is a pure, deterministic function of `supported_claim_ratio`, fabrication rate, and capped tool failures | §6.5 | `tests/test_verification_confidence.py` |
| AC-004-05 | `decide()`'s priority order: policy > unsupported-high-risk-claim > contradiction > confidence thresholds | B-2, B-3 | `tests/test_safety_abstention.py` |
| AC-004-06 | `check_input` flags known prompt-injection patterns and only those | G-5 | `tests/test_safety_output_safety.py` |
| AC-004-07 | `run_consultation`/`stream_consultation` return/yield `verification_report`/`abstention` as additive keys; an `abstain` decision replaces `final_answer`, a `partial` one prefixes it | B-1, B-4, B-5 | `tests/test_runtime_executor.py` |
| AC-004-08 | The five frozen SSE events and `ConsultResponse`/history persistence keep their pre-existing fields unchanged | B-1, G-7 | `tests/test_sse_contract.py`, `tests/test_api_agents.py` (both additively extended, not altered) |
| AC-004-09 | `RunState` is the executor's real internal state (not a dict); `ToolCall.tool`→wire `name` projection happens at exactly one function | G-6, B-8 | `tests/test_runtime_executor.py`, code inspection of `executor.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit — claims | extraction degradation, risk parsing | `tests/test_verification_claims.py` |
| Unit — evidence | tool-result normalization, score clamping, PubMed-vs-guideline content gap | `tests/test_verification_evidence.py` |
| Unit — verification | batched judge call, overlap downgrade, contradiction parsing | `tests/test_verification_verify.py` |
| Unit — confidence | pure formula table | `tests/test_verification_confidence.py` |
| Unit — abstention | priority-ordered decision table | `tests/test_safety_abstention.py` |
| Unit — output safety | injection heuristic true/negative cases | `tests/test_safety_output_safety.py` |
| Integration | executor wiring, RunState population, abstain/partial paths end-to-end | `tests/test_runtime_executor.py` |
| Frozen (additive only) | wire/persistence contracts unchanged in existing fields | `tests/test_sse_contract.py`, `tests/test_api_agents.py`, `tests/test_workflow.py` (untouched) |

## 10. Migration & Compatibility

Two new columns on `Consultation` (`data/schemas/__init__.py`):
`verification_report: JSON` and `abstention: JSON`, both defaulting to `{}`,
mirroring the existing `citation_report` pattern. Additive-only; no backfill
needed. Migration generated via `alembic revision --autogenerate` against a
clean local Postgres per `CLAUDE.md`'s documented workflow.

**`intelligence/agents/citation_guard.py` is explicitly *not* shimmed this
phase**, unlike the charter's original shim schedule for
`{citation_guard,explainability,risk_engine}.py`. It remains real,
unmodified implementation — now composed as a pre-filter ahead of the new
verifier (ADR-006), not replaced by it. Shimming/deleting it is deferred
until the new verifier has demonstrably absorbed its role in production
evals, tracked as a follow-up, not assumed complete on day one of this
phase.

`src/sephiroth/runtime/executor.py` adopts `RunState` as its real internal
accumulator, resolving the `SPEC-003` §10 deferral. The one friction point
flagged there — `ToolCall.tool` vs. the frozen wire's `name` — is resolved
by a single projection function (`_tool_call_wire`) at the SSE-yield/return
boundary; nothing else in the wire shape changes.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Cost/latency: 2 extra LLM round-trips per consultation (`extract_claims` + `verify_claims`) | Instrumented from day one via existing `AgentResult.tokens`/`latency_ms` fields — real data feeds H6, not an estimate |
| 2 | Confidence weights (0.5, 0.2, cap 3) and abstention thresholds (0.4, 0.65) are placeholders | Explicitly named tunable constants (§6.5); validating them against the eval harness is a follow-up, not assumed done here |
| 3 | Claims backed only by PubMed evidence (no abstract text) verify more weakly than guideline-backed claims | Documented limitation (NG via `harvest_evidence`'s docstring), not a bug — `search_pubmed` genuinely returns no passage content today |
| 4 | `risk_level` (coarse per-consultation risk) does not gate abstention, only claim-level risk does | Deliberate: the spec's invariant is claim-level, not consultation-level; `risk_level` stays available for future correlation analysis |
| 5 | The verifier is itself an LLM and can be wrong (ADR-006) | Mitigated by the token-overlap downgrade rule (B-7); still not a substitute for eventual NLI-entailment validation, deferred per ADR-006's own alternatives-rejected note |
| 6 | No batching-size limit on `verify_claims`'s single prompt — an answer with an unusually large number of claims could hit a token limit | Not addressed this phase (no chunking framework built); flagged for validation against real answer lengths before it becomes a real constraint |

## 12. References

- [ADR-006](../08-decisions/ADR-006-claim-level-verification.md)
- [ADR-008](../08-decisions/ADR-008-abstention.md)
- `docs/06-security/safety.md`
- `docs/specs/SPEC-003-agent-runtime.md` §10 (the `RunState` deferral this phase resolves)

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved. Scoped to Verification & Safety only (Phase 4b) — Context Engine (4a) deferred to its own spec. |
