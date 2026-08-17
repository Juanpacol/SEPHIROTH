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
| **State** | ✅ implemented | 📋 phase 4 |

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

## What is missing

The honest gap, in order of severity:

1. **No abstention.** The system always answers. Fabricated citations are
   stripped and the answer is returned anyway — including when what remains is
   unsupported. ([ADR-008](../08-decisions/ADR-008-abstention.md))
2. **No claim-content verification.** A real citation attached to a claim it
   does not support passes every current check.
   ([ADR-006](../08-decisions/ADR-006-claim-level-verification.md))
3. **No output risk classification.** Nothing asks whether a recommendation is
   dangerous.
4. **No contradiction detection.** Two agents can disagree — say, on a lab value
   — and the coordinator will synthesise over the conflict silently.
5. **No human-in-the-loop gate.** No high-risk path routes for review.
6. **No PHI detection or prompt-injection defence in output.**

## The target pipeline

```
answer → claims → verification → risk → policy → abstain? → answer or decline
```

with the invariant that an **unsupported high-risk claim** must trigger
abstention rather than a caveat. That signal already exists as a computable
contract property; nothing consumes it yet.

## How safety gets measured

Safety claims are only credible if falsifiable, so each maps to a metric in
[methodology.md](../07-research/methodology.md): unsafe answer rate, unsupported
high-risk claim rate, abstention rate **and** abstention precision, policy
violation rate.

Abstention rate alone is not a safety metric. A system that declines everything
scores perfectly and helps nobody, which is why the pair is always reported
together.
