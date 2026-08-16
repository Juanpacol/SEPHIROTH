# ADR-008 — Abstention as a first-class output

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** decided 0, executed 4

## Context

The system always answers. When the citation guard finds a fabricated citation
it strips it, marks the gap `[unverified — removed]`, and returns the answer
anyway. There is no path by which SEPHIROTH says *"I don't have enough evidence
for this."*

## Decision

An abstention engine producing a typed decision — `answer` / `partial` /
`abstain` — where abstaining **requires** a reason drawn from a closed set:

`insufficient_evidence` · `conflicting_evidence` ·
`unsupported_high_risk_claim` · `tool_failure` · `model_uncertainty` ·
`policy_restriction`

The contract enforces this: an `AbstentionDecision` cannot be constructed with
status `abstain` and no reason, nor with status `answer` and a reason.

## Rationale

- **In clinical decision support, silence beats a confident wrong answer.** This
  is the one place where refusing to be useful is the safe behaviour.
- **Reasons make abstention measurable.** Abstention precision per reason
  answers "does it decline for the right causes?" — a bare rate does not.
- **The inputs already exist as contracts:** `supported_claim_ratio`,
  `has_unsupported_high_risk_claim`, contradiction count, tool failures. The
  engine composes signals rather than inventing a judgement.
- Derived confidence, never self-reported. An LLM asked how confident it is
  produces a number uncorrelated with correctness, and
  [scope.md](../00-project/scope.md) rules out unmeasured confidence scores.

## Consequences

**Abstention rate and abstention precision must always be reported together.** A
system that abstains on everything achieves a perfect unsafe-answer rate and is
worthless. Reporting the rate alone would let that failure look like success —
which is why [methodology.md](../07-research/methodology.md) pins the pair.

Thresholds are a tunable, and tuning them is itself an experiment rather than a
constant to be guessed once.

The wire contract absorbs this additively: abstention arrives as a new field, and
the frontend ignores what it does not recognise.

## Alternatives rejected

**Always answer with a confidence score** — pushes the decision onto a user who
has less information than the runtime does.
**Threshold on an LLM self-reported confidence** — the number is not grounded in
anything observable.
