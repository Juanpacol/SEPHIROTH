# ADR-006 — Claim-level verification, not citation checking

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** decided 0, executed 4

## Context

The citation guard audits every citation label in an answer against actual tool
output, strips fabricated ones, and reports what it removed. It is genuinely
useful and it works.

## Problem

It verifies **provenance, not content**. It can confirm that
`[ADA Standards of Care, 2024]` was really retrieved. It cannot detect that the
sentence attached to that citation says something the guideline does not say.

In clinical decision support, a plausible sentence carrying a real citation is
more dangerous than a fabricated citation, because it survives inspection.

A second gap: `sanitize()` replaces a bad citation with `[unverified — removed]`
and **returns the answer anyway**. Nothing causes the system to decline.

## Decision

Decompose answers into individually verifiable claims and classify each against
retrieved evidence:

`SUPPORTED` · `PARTIALLY_SUPPORTED` · `UNSUPPORTED` · `CONTRADICTED` · `UNKNOWN`

The citation guard is retained as a **fast pre-filter feeding the verifier**,
not as the terminal check.

## Rationale

- **Five states, not two.** The distinction between *unsupported* (evidence is
  silent) and *contradicted* (evidence disagrees) is the difference between a
  gap and an error. Collapsing them discards the more urgent signal.
- **Claims, not sentences.** One sentence can carry several assertions, and
  clinical sentences routinely do.
- **A verdict per claim enables abstention.** `supported_claim_ratio` and
  "is there an unsupported high-risk claim?" are computable signals; an
  answer-level score is not actionable.
- There is already a working prototype: `faithfulness.py::judge_llm` decomposes
  answers per claim — but only offline, as an evaluation metric, and only
  binary. Phase 4 promotes it into the live path and widens its vocabulary.

## Consequences

An LLM call per claim, which is the dominant cost of the reliability mechanisms
and therefore the main subject of H6. Latency and token overhead must be
reported alongside grounding improvements, not separately.

Risk: **the verifier is itself an LLM and can be wrong.** Mitigated by reporting
judge agreement against a deterministic proxy, and by never letting a judge
verdict be sole evidence for a claim in the thesis.

## Alternatives rejected

**Keep citation checking only** — cannot detect misattributed content, the
failure mode that matters most here.
**Answer-level faithfulness score** — a single number gives the safety engine
nothing to act on.
**NLI entailment model** — plausible and cheaper per claim, but adds a model
dependency outside the provider abstraction. Worth revisiting once H6 quantifies
the LLM judge's cost.
