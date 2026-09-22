---
id: SPEC-004
title: Verification & Safety
phase: 4
version: 1.1.0
status: Draft
authors: [jbotero]
created: 2026-08-19
updated: 2026-09-22
supersedes: []
superseded_by: null
depends_on: [SPEC-000, SPEC-001, SPEC-002, SPEC-003]
adrs: [ADR-006, ADR-008, ADR-018]
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

**1.2.0 motivation.** `src/sephiroth/verification/evidence.py:29-32`
deliberately excludes a vision/imaging tool's own output
(`describe_medical_image`'s `description`, `analyze_medical_image`'s
`findings`) from `harvest_evidence` — "admitting those as evidence would let
an answer verify itself." Correct as far as it goes, but its only downstream
effect today is that a RadiologyAgent answer always harvests zero evidence.
`combined.py:218-228`/`verify.py:95-99` then mark every claim `UNKNOWN`,
`supported_claim_ratio` (§8, AC-004-04's formula) is 0/N, confidence is
`0.0`, and `abstention.decide` (B-3) fires `INSUFFICIENT_EVIDENCE` —
discarding a real, correct vision-model finding. Reproduced live
2026-09-22: `describe_medical_image` returned a genuine chest-x-ray
description; the consultation still abstained. `originating_agent` on the
resulting claims is also wrong (`"evidence"` instead of `"radiology"`) for
the same root reason — §6.2's extraction prompt only gives `'evidence'`/
`'drug_safety'` as examples, and with zero evidence signal the classifier
has nothing else to anchor a guess to. `check_drug_interactions` doesn't
have this problem because its `interactions` key is already in
`_EVIDENCE_LIST_KEYS` — this amendment gives RadiologyAgent an equivalent
path without weakening the anti-self-verification rule ADR-006 relies on.

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
- **G-8** (1.2.0) A claim that faithfully reports a perception tool's own
  output (vision description, imaging findings) is verifiable without being
  treated as independently corroborated — it must not silently degrade to
  `UNKNOWN`/zero confidence the way it does today.
- **G-9** (1.2.0) A claim asserting a finding the perception tool never
  reported (an invented/hallucinated finding) must still be classified
  `UNSUPPORTED` and, at high/critical risk, still abstain via the unchanged
  B-2 gate — this amendment must not weaken that invariant.

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
- **NG-7** (1.2.0) `VerificationStatus.OBSERVED` is never produced by the
  LLM judge — it is derived deterministically in code from which evidence
  ids a claim cites. Teaching the judge prompt to emit it directly is out of
  scope; that would reintroduce exactly the self-verification risk this
  amendment is designed to avoid.

## 5. Definitions

- **Claim** — one independently verifiable assertion extracted from an
  answer (`sephiroth.contracts.claims.Claim`).
- **Verdict** — a claim's `VerificationStatus` after judging it against
  evidence: `supported`, `partially_supported`, `unsupported`,
  `contradicted`, `unknown`, `observed` (1.2.0 — see §6.1).
- **Observation** — a perception tool's own direct output (a vision
  model's image description, an imaging model's structured findings),
  harvested separately from `EvidenceRecord`s built from retrieval/lookup
  tools (1.2.0 — see §6.2). Faithfully reporting an observation is
  verifiable without corroborating it against an independent source.
- **Abstention** — the runtime's `answer`/`partial`/`abstain` decision for
  one consultation (`sephiroth.contracts.safety.AbstentionDecision`).

## 6. Contracts

### 6.1 Types

No contract types change shape. This phase *populates* Phase 0 contracts
that were previously unused at runtime: `Claim`, `Contradiction`,
`VerificationReport`, `EvidenceRecord`, `SafetyFlag`, `AbstentionDecision`,
and — for the first time — `RunState`/`ToolCall`/`AgentResult` as the
executor's actual internal state (not a plain dict).

**1.2.0 additive change** (`sephiroth.contracts.enums.VerificationStatus`):

```python
class VerificationStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"
    OBSERVED = "observed"  # new — faithful to a tool's own perception output
```

`EvidenceRecord.source_type` (`sephiroth.contracts.enums.SourceType`) already
defines `TOOL_OUTPUT` and `MODEL_PRIOR` (unused until now) — `TOOL_OUTPUT` is
adopted to tag records built from `harvest_observations` (§6.2), so an
`OBSERVED` verdict's cited evidence is always distinguishable at read time
from a `GUIDELINE`/`LITERATURE` record. No enum member is added, removed, or
retyped elsewhere — this is a MINOR, additive change (SPEC-000 §6.3).

`VerificationReport` (`sephiroth.contracts.claims`) gains one property,
alongside the unchanged `supported_claim_ratio`:

```python
OBSERVED_WEIGHT: float = 0.6  # verification/confidence.py

class VerificationReport(BaseModel):
    ...
    @property
    def grounded_claim_ratio(self) -> float:
        """Like `supported_claim_ratio`, but counts an OBSERVED claim as
        OBSERVED_WEIGHT rather than 0 — faithful-to-tool-output claims
        aren't corroborated, but they aren't baseless either."""
```

`supported_claim_ratio` keeps its exact current meaning (`SUPPORTED`-only) —
it is still what `platform/api/routers/agents.py`'s `_persist` and
`platform/api/routers/dashboard.py` read and persist. Nothing that reads
`supported_claim_ratio` today changes behavior.

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

**1.2.0 additive change** — one new function, same module:

```python
def harvest_observations(tool_calls: list[ToolCall]) -> list[EvidenceRecord]:
    """Builds EvidenceRecord(source_type=TOOL_OUTPUT) entries from a
    perception tool's own successful output — describe_medical_image's
    `description` (status == "ok", non-empty), analyze_medical_image's
    `findings` (status == "ok", non-empty list). "unavailable" and
    "model_not_configured" results (the documented degraded-mode shapes,
    §6.4) produce nothing, same as a missing key. Kept as a function
    separate from harvest_evidence, not a new key in
    _EVIDENCE_LIST_KEYS — so `harvest_evidence` alone still returns []
    for these tool results (AC-004-13 pins this)."""
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

`harvest_observations` never raises: a missing/malformed tool result key,
`status: "unavailable"`, or `status: "model_not_configured"` all produce no
observation for that call, the same fail-open posture as `harvest_evidence`.
A consultation with an unusable perception-tool result therefore has no
observations and behaves exactly as it does today (marks claims `UNKNOWN` if
there's no other evidence either) — this amendment only changes behavior
when the perception tool actually succeeded.

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
| `OBSERVED_WEIGHT` | `verification/confidence.py` | 0.6 | tunable (1.2.0) — chosen so an all-`OBSERVED` answer's confidence (0.6) lands inside `[ABSTAIN_THRESHOLD, PARTIAL_THRESHOLD)`, i.e. always `partial`, never `abstain` or a silent full `answer` |

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
- **B-9** (1.2.0) `VerificationStatus.OBSERVED` MUST only be assigned by
  deterministic code (never emitted directly by a `generate_json` judge
  call) — a claim's verdict becomes `OBSERVED` only when the judge's own
  verdict is `supported` or `partially_supported` AND every evidence id it
  cites belongs to a `harvest_observations`-built record
  (`source_type == TOOL_OUTPUT`), and it still passes the existing B-7
  overlap check (a claim that fails `_overlap_supports` against an
  observation is `UNKNOWN`, exactly as it would be against any other
  evidence).
- **B-10** (1.2.0) `compute_confidence` uses `grounded_claim_ratio`, not
  `supported_claim_ratio`, as its base ratio. `supported_claim_ratio` itself
  is unchanged and still drives the persisted metric (§6.1) — only the
  input to the confidence/abstention formula changes.
- **B-11** (1.2.0) A claim with no matching observation or evidence record
  at all (an assertion the answering agent made up) is classified
  `UNSUPPORTED`, never `OBSERVED` or `UNKNOWN` — B-2's
  `has_unsupported_high_risk_claim` override is unchanged and still fires
  at high/critical risk regardless of how many other claims are `OBSERVED`.
- **B-12** (1.2.0) `harvest_evidence` and `harvest_observations` MUST be
  called and reasoned about separately — an `OBSERVED` record is never
  added to the list `harvest_evidence` returns, so
  `test_model_generated_tool_output_is_never_treated_as_evidence` (existing,
  `tests/test_verification_evidence.py`) keeps passing unmodified.

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
| AC-004-10 | `harvest_observations` returns a `TOOL_OUTPUT` record for a successful `describe_medical_image`/`analyze_medical_image` result, and `[]` for `"unavailable"`, `"model_not_configured"`, or an `{"error": ...}` result | §6.2, §6.4 | `tests/test_verification_evidence.py` |
| AC-004-11 | A claim faithfully restating an observation's content, with all cited ids from `TOOL_OUTPUT` records, is classified `OBSERVED` | B-9 | `tests/test_verification_combined.py`, `tests/test_verification_verify.py` |
| AC-004-12 | A claim asserting a finding absent from every observation and evidence record is classified `UNSUPPORTED`; at high/critical risk it still triggers abstention via the unchanged B-2 gate | B-11, G-9 | `tests/test_safety_abstention.py`, `tests/test_runtime_executor.py` |
| AC-004-13 | `harvest_evidence([describe_medical_image_result])` still returns `[]` (existing behavior, unmodified) | B-12 | `tests/test_verification_evidence.py` |
| AC-004-14 | An answer whose claims are entirely `OBSERVED` yields `grounded_claim_ratio == OBSERVED_WEIGHT` and a `partial` decision (never `abstain`, never a plain `answer`) | B-10, §6.5 | `tests/test_verification_confidence.py`, `tests/test_safety_abstention.py` |
| AC-004-15 | A radiology consultation's claims carry `originating_agent == "radiology"`, not `"evidence"` | §2 (1.2.0 motivation) | `tests/test_runtime_executor.py` |

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
| Unit — observations (1.2.0) | `harvest_observations` per tool/status-shape table | `tests/test_verification_evidence.py` |
| Unit — grounded confidence (1.2.0) | `grounded_claim_ratio`, `OBSERVED_WEIGHT` formula table | `tests/test_verification_confidence.py`, `tests/test_contracts_models.py` |
| Integration — radiology (1.2.0) | RadiologyAgent consultation end-to-end: `OBSERVED` claims, `originating_agent`, `partial` outcome, invented-finding abstention | `tests/test_runtime_executor.py`, `tests/test_abstention_replay.py` |

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

**1.2.0 — no migration needed.** `verification_report`/`abstention` are
plain `JSON` columns (§10, 1.0.0) with no Postgres enum type backing
`VerificationStatus` — adding `OBSERVED` is a new string value inside JSON,
not a schema change. Pre-1.2.0 persisted rows remain valid (they simply
never contain `"observed"`). `safety/abstention.py`'s `_ABSTAIN_MESSAGES`
gains one PARTIAL-reason banner (distinct from the existing generic
`PARTIAL_BANNER`) for the "answer rests on observed, not corroborated,
claims" case — every `AbstentionReason` a PARTIAL decision can carry MUST
have a message entry, or it raises `KeyError` (existing invariant,
unchanged, just now covering one more reason value).
`intelligence/evaluation/abstention_replay.py`, which calls
`harvest_evidence`/`verify_claims`/`compute_confidence`/`decide` directly
(bypassing the executor), is updated to also call `harvest_observations` —
otherwise the replay path would silently diverge from live behavior for any
future imaging/vision golden case.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Cost/latency: 2 extra LLM round-trips per consultation (`extract_claims` + `verify_claims`) | Instrumented from day one via existing `AgentResult.tokens`/`latency_ms` fields — real data feeds H6, not an estimate |
| 2 | Confidence weights (0.5, 0.2, cap 3) and abstention thresholds (0.4, 0.65) are placeholders | Explicitly named tunable constants (§6.5). The replay wiring to validate them now exists (`intelligence/evaluation/abstention_replay.py`, `runner.run_full_mode`), but the committed `results/latest.json` snapshot has no real numbers yet — recomputing it requires a live model call this environment has no key for (same constraint `faithfulness_llm_judge` already has). `abstention_recall`/`abstention_precision` are computed and reported but deliberately **not gated** in `thresholds.json` yet — gating on an absent/`None` value would hard-fail every CI run. Gating is a follow-up once the user runs `--mode full --record` with a real key. |
| 3 | Claims backed only by PubMed evidence (no abstract text) verify more weakly than guideline-backed claims | Documented limitation (NG via `harvest_evidence`'s docstring), not a bug — `search_pubmed` genuinely returns no passage content today |
| 4 | `risk_level` (coarse per-consultation risk) does not gate abstention, only claim-level risk does | Deliberate: the spec's invariant is claim-level, not consultation-level; `risk_level` stays available for future correlation analysis |
| 5 | The verifier is itself an LLM and can be wrong (ADR-006) | Mitigated by the token-overlap downgrade rule (B-7); still not a substitute for eventual NLI-entailment validation, deferred per ADR-006's own alternatives-rejected note |
| 6 | No batching-size limit on `verify_claims`'s single prompt — an answer with an unusually large number of claims could hit a token limit | Not addressed this phase (no chunking framework built); flagged for validation against real answer lengths before it becomes a real constraint |
| 7 | (1.2.0) `OBSERVED_WEIGHT = 0.6` is a placeholder, same tuning status as the other confidence/abstention constants (risk 2) | Chosen deliberately to land inside the PARTIAL band under today's thresholds (§6.5); revisit alongside those constants once real calibration data exists |
| 8 | (1.2.0) A vision/imaging model can itself misperceive the image; `OBSERVED` only proves the answer is faithful to what the tool said, not that the tool was right | Explicitly why `OBSERVED` weights below `SUPPORTED` (never full confidence) and the banner (§10) always names the answer as AI-derived and needing professional review — unchanged clinical safety posture, just correctly labeled instead of wrongly abstained |

## 12. References

- [ADR-006](../08-decisions/ADR-006-claim-level-verification.md)
- [ADR-008](../08-decisions/ADR-008-abstention.md)
- [ADR-018](../08-decisions/ADR-018-observation-grounded-verification.md) — 1.2.0
- `docs/06-security/safety.md`
- `docs/specs/SPEC-003-agent-runtime.md` §10 (the `RunState` deferral this phase resolves)

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-19 | Initial version; implemented in the same phase it was approved. Scoped to Verification & Safety only (Phase 4b) — Context Engine (4a) deferred to its own spec. |
| 1.1.0 | 2026-08-19 | Added the abstention-replay eval wiring (`intelligence/evaluation/abstention_replay.py`) that risk 2 originally flagged as missing — computes `abstention_recall`/`abstention_precision` against the golden dataset's 4 `adversarial-negative` cases, reported but not yet gated (no real committed data to gate against). Real calibration remains a follow-up. |
| 1.1.0 (Draft, 1.2.0 pending) | 2026-09-22 | `SF065`: drafted the 1.2.0 amendment — `VerificationStatus.OBSERVED` (ADR-018), `harvest_observations`/`grounded_claim_ratio`/`OBSERVED_WEIGHT`, new §7 rules B-9..B-12, new AC-004-10..15 — so a RadiologyAgent answer faithful to a vision/imaging tool's own output returns `partial` with an observation banner instead of abstaining on `INSUFFICIENT_EVIDENCE`. Status held at `Draft` (not `Implemented`) until `SF066` (tests) and `SF067` (code) land, per `SPEC-000` B-2/B-4 — the new ACs have no test yet. Additive only — no existing §6 contract removed or retyped, no migration. |
