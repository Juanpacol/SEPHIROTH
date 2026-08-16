# ADR-005 — Hybrid retrieval with reciprocal rank fusion

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** 0 (records an existing decision)

## Context

Evidence retrieval runs over a corpus of clinical guideline excerpts. Clinical
queries arrive both as precise terminology (*"SGLT2 inhibitor eGFR threshold"*)
and as lay paraphrase (*"kidney medicine for diabetics"*).

## Decision

Fuse keyword-overlap scoring with dense Gemini embeddings via **reciprocal rank
fusion** (RRF, k=60), weighting dense 2× over keyword, with a cosine floor of
0.70. Retrieval degrades silently to keyword-only if embeddings are unavailable.

## Rationale

- The two strategies fail differently. Keyword matching misses paraphrase; dense
  retrieval misses exact clinical terms and rare tokens. The benchmark contains
  both a `golden` and a `paraphrase` category precisely because both matter.
- **Dense is weighted higher because keyword scoring is not IDF-weighted** and
  therefore over-ranks short documents dense in common words.
- RRF fuses ranks, not scores, so the two strategies' incomparable scales never
  need normalising.

## Measured result

Recall@1 rose 0.78 → **0.97**; Recall@3/@5 and MRR reached **1.00**. Thresholds
were raised accordingly rather than left slack.

The 0.70 similarity floor was **calibrated empirically, not chosen**: real
adversarial queries that are topically on-topic (*"homeopathic remedy for septic
shock"*) score 0.65–0.70, overlapping the low end of genuine matches. The floor
separates them from top-1 relevant matches at 0.73+.

Detecting *"this recommends a pseudo-scientific treatment"* is deliberately left
to the citation guard, not the retriever. A retriever's job is topical
relevance; safety is a different concern with a different failure cost.

## Consequences

Embeddings are a dependency, mitigated by a committed, hash-checked artifact so
CI runs offline and deterministically.

**The result is corpus-bounded.** With 22 documents, near-perfect recall says as
much about the corpus as the method. H2 must be reported with corpus size
attached, and this is listed as a threat to validity in
[methodology.md](../07-research/methodology.md).

## Alternatives rejected

**Dense only** — fails on rare clinical terms; the paraphrase gain does not
offset it.
**Keyword only** — the pre-existing baseline, at 0.78 Recall@1.
**A second vector database** — no experimental justification, and
[scope.md](../00-project/scope.md) rules out unjustified infrastructure.
