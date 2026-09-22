# ADR-018 — Observation-grounded verification for perception-tool claims

**Status:** Accepted · **Date:** 2026-09-22 · **Phase:** decided 4 (amends `SPEC-004`, pending `SF067`)

## Context

`src/sephiroth/verification/evidence.py:29-32` excludes a perception tool's
own output — `describe_medical_image`'s `description`, `analyze_medical_image`'s
`findings` — from the evidence pool `harvest_evidence` builds:

> "imaging's `findings` and vision's `description` are the model's *own*
> output, and admitting those as evidence would let an answer verify
> itself."

That reasoning is correct on its own terms and this decision does not
reverse it. But its only production effect today is that a RadiologyAgent
consultation always harvests zero evidence, because `RadiologyAgent`'s
entire grounding is that same excluded tool output. With no evidence,
`combined.py`/`verify.py` mark every claim `UNKNOWN` (`ADR-006`'s own
five-state vocabulary, working exactly as designed), `supported_claim_ratio`
is `0/N`, `compute_confidence` (`ADR-008`) returns `0.0`, and
`abstention.decide` fires `INSUFFICIENT_EVIDENCE` — discarding a real,
correct finding. Reproduced live 2026-09-22 against `qwen2.5vl:3b`: a
genuine chest-x-ray description was returned by the tool, and the
consultation still abstained.

`DrugSafetyAgent` never hits this: `check_drug_interactions`'s
`interactions` key is already in `_EVIDENCE_LIST_KEYS`, so its answers
verify normally. Radiology has no equivalent path.

## Problem

The verifier conflates two different questions:

1. **Corroboration** — does an independent source (a guideline, a paper, a
   curated interaction table) agree with this claim? This is what
   `harvest_evidence` correctly guards against self-verifying.
2. **Faithfulness** — did the answering agent accurately report what a
   *separate tool call* actually returned? This is the same category of
   check `citation_guard` already performs for RAG citations — auditing an
   answer against real tool output — and it does not require the tool's
   output to itself be independently corroborated to be a meaningful check.

Excluding perception-tool output from evidence conflates (2) with (1) and
throws away (2) entirely, so there is no way to distinguish "faithfully
reported a real finding" from "reported nothing at all" — both currently
collapse into the same `UNKNOWN`/zero-confidence outcome.

## Decision

Add a fifth-plus state, `VerificationStatus.OBSERVED`, meaning "faithful to
a perception tool's own output, not independently corroborated" — strictly
weaker than `SUPPORTED`, strictly stronger than `UNKNOWN`. It amends
`SPEC-004` (§6.1, §7 B-9..B-12) rather than a new spec, since it does not
remove or retype anything in `SPEC-004`'s existing contracts (MINOR bump,
`SPEC-000` §6.3).

- `harvest_observations(tool_calls)`, new and separate from
  `harvest_evidence`, builds `EvidenceRecord(source_type=TOOL_OUTPUT)`
  entries from a perception tool's successful result only. `harvest_evidence`
  is unchanged — a perception tool's output still never appears in the list
  it returns, so `ADR-006`'s guard holds exactly as before.
- `OBSERVED` is assigned deterministically in code, never emitted by the LLM
  judge: a claim already judged `supported`/`partially_supported`, whose
  cited evidence ids are *all* `TOOL_OUTPUT` records, becomes `OBSERVED`
  instead. A claim citing nothing (an invented finding) stays `UNSUPPORTED`,
  and at high/critical risk `ADR-008`'s `has_unsupported_high_risk_claim`
  gate still fires unchanged.
- `grounded_claim_ratio` (`OBSERVED` weighted at `OBSERVED_WEIGHT = 0.6`,
  `SUPPORTED` at 1.0) replaces `supported_claim_ratio` as
  `compute_confidence`'s input. `0.6` lands inside `[ABSTAIN_THRESHOLD,
  PARTIAL_THRESHOLD)` under today's thresholds, so an all-`OBSERVED` answer
  is always `partial`, never `abstain`, never a plain `answer` presented as
  fully verified. `supported_claim_ratio` itself is unchanged — it still
  drives the persisted metric untouched.
- A `partial` decision driven by `OBSERVED` claims carries a distinct
  banner naming the answer as an AI visual description, not independently
  verified, requiring professional review — never the generic partial
  banner, so a clinician can tell the two `partial` reasons apart.

## Rationale

- **Faithfulness and corroboration are genuinely different checks**, and
  `citation_guard` already proves the pattern works: verifying that an
  answer accurately reflects a tool's own output is not the tool
  "verifying itself" — it's checking the *answering agent* didn't
  misreport or invent beyond what the tool said.
- **The failure mode this fixes is worse than the one it's mistaken for.**
  Discarding a correct, tool-grounded clinical finding as
  `INSUFFICIENT_EVIDENCE` is itself a safety problem — it trains a
  clinician to distrust or ignore a working feature, and it's strictly less
  safe than showing the same finding with an honest "not independently
  verified" caveat.
- **`OBSERVED` cannot upgrade to `SUPPORTED`** by any code path — it is a
  ceiling, not a stepping stone, keeping the self-verification boundary
  `ADR-006` established intact.
- **Deterministic assignment, not a judge label**, keeps the one thing
  `ADR-006`'s "the verifier is itself an LLM and can be wrong" risk already
  worries about from getting worse — the model never gets to grant itself
  `OBSERVED`, only to have a claim's cited-ids checked against records the
  code already knows are `TOOL_OUTPUT`.

## Consequences

- Radiology (and any future perception-tool agent) answers that faithfully
  report a real finding return `partial` with a specific banner instead of
  `abstain`. A radiology answer can never again return a plain, unqualified
  `answer` purely from tool observation — it is always at most `partial`,
  by construction, since `OBSERVED` never reaches `1.0`.
- An invented finding (asserted, but absent from every observation and
  evidence record) is unaffected: still `UNSUPPORTED`, still triggers
  abstention at high/critical risk via the unchanged `ADR-008` gate.
- `intelligence/evaluation/abstention_replay.py` must also call
  `harvest_observations`, or the offline replay path silently diverges from
  live executor behavior for any imaging/vision golden case added later.
- `OBSERVED_WEIGHT = 0.6` is a placeholder with the same tuning status as
  `SPEC-004`'s other confidence/abstention constants (no live-model
  calibration data exists yet) — revisit together.

## Alternatives rejected

**Add `describe_medical_image`'s `description`/`analyze_medical_image`'s
`findings` directly to `_EVIDENCE_LIST_KEYS`**, treating them exactly like
`search_clinical_guidelines`'s `results` — rejected: this would let a
`supported` verdict be reached from a claim citing only the tool's own
output, exactly the self-verification `ADR-006`'s comment warns against.
`OBSERVED` exists specifically to give partial credit without ever reaching
full `SUPPORTED` weight.

**Special-case RadiologyAgent in `abstention.decide`** (e.g. "never abstain
on `INSUFFICIENT_EVIDENCE` for this one agent") — rejected: it would bypass
the confidence mechanism entirely for one agent rather than fixing what the
mechanism measures, and would equally excuse a truly invented finding with
no observation behind it, which the confidence-based fix does not.

**Author a new spec instead of amending `SPEC-004`** — rejected once the
existing precedent was found: `SPEC-005` (1.0.0→1.1.0) and `SPEC-006`
(1.1.0→1.2.0, 1.0.0→1.1.0) both amended the spec that already owns the
contract being extended, keeping the same phase number, rather than
minting a new phase/spec for an additive change to existing contracts.
