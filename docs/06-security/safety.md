# Clinical safety

Safety here means **the safety of what the system says**, which is distinct from
security ([threat-model.md](threat-model.md)) and from privacy
([privacy.md](privacy.md)).

## Standing position

SEPHIROTH is decision **support**, not an autonomous clinician. Every
recommendation requires professional review, every answer carries a disclaimer,
and every factual claim must cite its source. This is baked into the system
prompt of every agent, not left to the model's discretion.

## Two engines, deliberately separate

They are easy to conflate and answer different questions.

| | Risk engine | Safety engine |
|---|---|---|
| **Assesses** | patient data | model output |
| **Asks** | "is this lab value dangerous?" | "is this answer safe to show?" |
| **Method** | deterministic thresholds | claims, policies, risk classification |
| **State** | ✅ implemented | ✅ implemented (`sephiroth.safety.abstention`) |

They never talk to each other: `risk.py`'s flags feed only the patient-record
risk badge (`patients.py`, `dashboard.py`), never `abstention.py`'s `decide()`.
A "high" patient risk level and an "abstained" AI answer are unrelated
signals that happen to share the word "risk."

`risk_engine.py` is genuinely useful clinical logic and is kept. It is simply
not output safety, and calling it that would overstate what the system does
today.

## What exists now

| Control | Mechanism |
|---|---|
| Mandatory citations | Every agent prompt requires `[Source, Year]` or `[PMID:x]` |
| Citation provenance | `citation_guard.audit()` against real tool output |
| Fabrication removal | `sanitize()` replaces unverifiable citations, and reports them |
| Adversarial evaluation | 4 benchmark cases with no supporting guideline at all |
| Patient risk flags | Curated lab and medication thresholds |
| Tool confinement | Whitelist enforced at dispatch |
| Disclaimer | On every answer and every page |

## Abstention: hard stops vs. tunable thresholds

`sephiroth.safety.abstention.decide()` (`ADR-008`) is the actual gate on every
AI answer, checked in this priority order — an earlier, non-negotiable check
overrides a later, tunable one:

| Check | Kind | Overrides confidence? |
|---|---|---|
| `prompt_injection` input flag | **hard stop** (policy) | Yes — abstains regardless of how confident the answer is |
| `has_unsupported_high_risk_claim` | **hard stop** | Yes — an answer that "sounds confident" but asserts one unsupported high-risk claim must still abstain (the invariant `abstention.py`'s own docstring calls out) |
| Any `contradictions` between claims/evidence | **hard stop** | Yes |
| `confidence < ABSTAIN_THRESHOLD` (0.4) | **tunable score** | Abstains only via this threshold, not a fixed rule |
| `confidence < PARTIAL_THRESHOLD` (0.65) | **tunable score** | Downgrades to `partial` (caveat banner), not a full abstention |

The three hard stops are structural — no threshold tuning changes whether
they fire. The two thresholds are explicitly flagged in code as an
experiment ("tuning them is itself an experiment — validate against the eval
harness before hardening further") — they're the only part of this gate
that's a judgment call rather than a rule.

`risk.py`'s `LAB_RULES`/drug-interaction table has **no hard-stop
equivalent** — every rule there only ever produces a display flag
(`severity: "high"|"medium"`) that feeds `assess_risk_level()` for the
patient-record badge. No lab value or drug interaction, however severe, ever
blocks or alters an AI answer directly; it isn't wired into `abstention.py`
at all. If a future spec wants patient risk to influence AI caution (e.g.
lower the abstain threshold for a patient already flagged "high risk"), that
link doesn't exist yet — it would be new code, not a config change.

## What is missing

The honest gap, in order of severity:

1. **Claim-content verification is implemented** (`sephiroth.verification`,
   `ADR-006`) — closes the "real citation, wrong claim" gap the
   citation-label-only check couldn't catch on its own. Listed here only
   because this doc previously called it missing; no longer a gap.
2. **No output risk classification beyond claim risk.** Claims carry a
   `risk: RiskLevel` used by the unsupported-high-risk-claim check above, but
   nothing classifies a *recommendation* (e.g. a specific drug/dose) as
   dangerous independent of whether its claims are cited.
3. **No contradiction detection between specialist agents' own outputs** —
   `contradictions` in `VerificationReport` catches claim-vs-evidence
   conflicts; two specialists disagreeing with each other (not with retrieved
   evidence) isn't a checked case.
4. **No human-in-the-loop gate.** No high-risk path routes for review before
   an answer reaches a clinician.
5. **No PHI detection or prompt-injection defence in output** (input-side
   prompt-injection is checked — see the hard-stop table above; the
   `sephiroth.safety` heuristic is input-only).

## The pipeline, as implemented

```
answer → citation_guard (sanitize) → claims → verification → abstention.decide() → answer | partial | abstain
```

matching the target pipeline this doc previously described as aspirational —
the invariant that an **unsupported high-risk claim** must trigger abstention
rather than a caveat is implemented, not just a documented intent (see the
hard-stop table above).

## How safety gets measured

Safety claims are only credible if falsifiable, so each maps to a metric in
[methodology.md](../07-research/methodology.md): unsafe answer rate, unsupported
high-risk claim rate, abstention rate **and** abstention precision, policy
violation rate.

Abstention rate alone is not a safety metric. A system that declines everything
scores perfectly and helps nobody, which is why the pair is always reported
together.
