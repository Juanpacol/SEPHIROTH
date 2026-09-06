---
id: SPEC-026
title: The Landing Page Says What The Product Is
phase: 24
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-018, SPEC-022, SPEC-023, SPEC-024, SPEC-025]
adrs: []
features: [F-108, F-109]
diagrams: []
---

# SPEC-026 — The Landing Page Says What The Product Is

## 1. Summary

Content only. The landing page, its components and its interactive demos are
kept exactly as they are; the words are rewritten to describe the product that
exists now rather than the one that existed eight phases ago, and a test is
added so the two cannot drift apart again.

## 2. Motivation

The page sells a consultation copilot: multi-agent routing, citation guard,
claim verification, abstention. All of that is real and all of it still works.
None of it is what a clinic would buy the product for today.

Since it was written, the product gained a unified task inbox, a work centre,
the clinical encounter with AI-assisted notes, results with a closed loop, and
— the biggest one — **local inference by default**. The page mentions none of
them.

One line is worse than stale. `marketing.faq.a2`, answering "what data does it
see", said:

> Consulta el aviso de privacidad en el README del proyecto para saber
> exactamente qué sale de la máquina.

Since SPEC-022 the answer is "nothing, by default", and the README it points at
now says so. A page that sends a reader elsewhere for an answer it could give —
and that reads as evasive precisely where the product is now strongest — is
losing the sale on its best feature.

## 3. Goals

- **G-1** The page describes what a clinic gets today.
- **G-2** The privacy story is on the page and near the top, because it is the
  first question a clinic asks.
- **G-3** No claim on the page is one the product cannot back.
- **G-4** Copy and product cannot drift apart silently again.

## 4. Non-Goals

- **NG-1** **No new page, no redesign, no new components.** The existing
  layout, the demos (`ConsultationWalkthrough`, `ClaimVerifier`,
  `CitationGuardToggle`, `AbstentionGate`, `AnalysisGallery`) and the brand
  treatment are kept. Two content sections are added using the section patterns
  already on the page.
- **NG-2** No metrics. There is no measurement behind "saves N hours", so it is
  not written. A number a reader can check is worth more than one they cannot.
- **NG-3** No compliance claim. Local inference removes one exposure; it is not
  a HIPAA or GDPR programme, and the page says so where a reader might infer
  otherwise.
- **NG-4** No pricing, no lead form, no analytics. Those are a commercial
  decision, not a content edit.
- **NG-5** The gradient rule is untouched: `sephiroth` gradient appears only on
  mock AI-output cards inside the demos, never on the hero or the chrome.

## 5. Definitions

- **Marketing copy** — every `marketing.*` key in both dictionaries.
- **A backed claim** — a sentence whose truth a test can tie to code.

## 6. Contracts

### 6.1 Types

`N/A` — no schema, no API, no new component types.

### 6.2 Interfaces

`N/A`. The page's routes and anchors are unchanged except one addition:
`#privacy`, which the nav links to first.

### 6.3 State machine

`N/A`.

### 6.4 Errors

`N/A`.

### 6.5 Configuration

`N/A`. The page reads no settings; the *test* reads two of them (§7 B-2).

## 7. Behaviour

- **B-1** The three pain points MUST describe the scattered inbox, the results
  nobody closed, and the note that eats the evening — the problems phases 16–24
  actually solved.
- **B-2** The privacy claim ("nothing leaves by default") MUST be tied by test
  to `llm_provider == "ollama"` and `ai_allow_phi is False`.
- **B-3** The copy MUST NOT claim HIPAA or GDPR compliance, FDA approval, or
  clinical validation, in either language.
- **B-4** The "not a medical device" badge MUST remain.
- **B-5** The privacy section MUST state what running locally is *not*.
- **B-6** No copy outside the worked clinical example MUST carry a percentage
  or a customer count.
- **B-7** Copy replaced by this phase MUST be removed from both dictionaries,
  not left orphaned.
- **B-8** Both dictionaries MUST stay in lockstep — enforced by the parity test
  that already exists.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-026-01 | The privacy promise is tied to the defaults and the guards that make it true | B-2 | `tests/test_landing_claims.py::TestThePrivacyPromiseIsTrue` |
| AC-026-02 | No forbidden claim, the medical-device badge survives, and the disclaimer stays | B-3, B-4, B-5, B-6 | `tests/test_landing_claims.py::TestClaimsAClinicalProductMustNotMake` |
| AC-026-03 | The new sections exist in both languages and the replaced copy is gone | B-1, B-7 | `tests/test_landing_claims.py::TestTheCopyDescribesTheProductThatExists` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Copy vs code | every claim the product has to back | `tests/test_landing_claims.py` |
| Copy vs copy | both dictionaries hold the same keys | `lib/__tests__/i18n.test.ts` (existing) |

## 10. Migration & Compatibility

No schema, no API, no migration. Seventeen `marketing.*` keys are rewritten in
place, eleven are removed, and thirty-five are added — in both dictionaries, so
the parity test passes throughout.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Copy drifts from the product again | That is what this phase is fixing and what `test_landing_claims.py` guards. It cannot catch every drift — a test cannot know that "one inbox" stopped being true — but it catches the claims that would be actively false, which are the ones that matter |
| 2 | Leading with privacy may read as defensive to a reader who was not worried | Accepted. It is the first question every clinic asks about AI, and answering it before it is asked is the opposite of defensive |
| 3 | The page is longer than it was | Two sections longer, and both earn it: the privacy section is the strongest differentiator and was absent, and "what a Tuesday looks like" is the only place the page describes daily use at all |
| 4 | Copy is maintained in two languages by hand | Unchanged from before this phase, and the parity test already fails a build that forgets one |
| 5 | A forbidden-phrase list is a blunt instrument | It is, and deliberately: it catches the specific sentences a clinical product must never write. It is not a claim reviewer, and §11 risk 1 says what it cannot do |

## 12. References

- `docs/specs/SPEC-022-local-ai.md` — the default the privacy claim rests on.
- `docs/specs/SPEC-024-results-loop.md` — the guard behind "cannot be marked
  done until they have been told".
- `docs/08-decisions/ADR-016-signing-is-the-review-gate.md` — the gate behind
  "nothing reaches the chart until you sign it".

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
