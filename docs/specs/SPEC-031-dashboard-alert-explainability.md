---
id: SPEC-031
title: Dashboard Alert Explainability and Visual Summary
phase: 16
version: 0.1.0
status: Approved
authors: [jbotero]
created: 2026-09-26
updated: 2026-09-26
supersedes: []
superseded_by: null
depends_on: [SPEC-000]
adrs: [ADR-019]
features: [F-044]
diagrams: []
---

# SPEC-031 — Dashboard Alert Explainability and Visual Summary

## 1. Summary

Makes every dashboard signal explain itself, and gives the dashboard a
visual summary that carries information rather than decoration.

- **Backend.** Every risk flag gains structured, machine-readable fields:
  `rule_code` and `factors` (test, value, comparator, threshold, unit).
  `/api/dashboard/action-items` items gain three fields:
  - `rule_code`/`factors`: why the signal fired.
  - `trend`: the last readings of the triggering test.
  - `recurrence`: how long an alert has been active, and whether it has
    happened before.

  All additions are additive. Existing labels, details, alert
  de-duplication and every existing response field are untouched.
- **Frontend.** Four new pieces:
  - a risk-distribution bar replacing the three flat Critical/Moderate/Stable
    boxes;
  - per signal, a value-vs-threshold range bar, a mini trend line, a
    recurrence chip and a one-line clinical explanation in the active
    language;
  - a two-column layout on large screens.

  All are hand-rolled SVG/CSS (ADR-019).

## 2. Motivation

The dashboard tells a clinician *what* fired but not *why*, *whether it is
getting worse* or *whether it is new*. That is the core job of a clinical
decision support system.

- **The explanation is buried in text.** An alert row renders
  `title — detail` (`platform/frontend/components/action-items-list.tsx:48-49`).
  The threshold that fired lives only inside an English format string such as
  `"Potassium {value} mEq/L (> 5.5)"` (`src/sephiroth/safety/risk.py:47`).
  - It cannot be translated. `SF069` explicitly deferred this.
  - It cannot be drawn.
  - The frontend could only extract it with a regex, which breaks silently
    whenever the wording changes.
- **No trajectory.** The dashboard shows the latest value only. The
  per-test history already exists (`LabResult`, indexed on
  `(patient_id, test_name, taken_at)`) and is drawn one click away on the
  patient page (`platform/frontend/components/patients/lab-trend-card.tsx:18`),
  but never next to the alert that it explains.
- **No acute vs. sustained distinction.** An alert active for three days and
  one raised an hour ago look identical. The data to tell them apart exists
  (`Alert.created_at`, `resolved_at`, status history), but no endpoint exposes
  it.
- **Numbers without proportion.** Critical/Moderate/Stable are three separate
  boxes (`platform/frontend/app/dashboard/page.tsx:40-43`), and the
  proportion has to be worked out mentally.

Explicitly **not** motivated here: a percentage "confidence" per alert. The
engine is deterministic, so a threshold either fires or it does not.
Displaying a probability would invent precision the system does not have
(ADR-019).

## 3. Goals

- **G-1** Every risk flag states its firing rule and the measured value against
  the threshold in structured fields (AC-031-01..04).
- **G-2** Every dashboard alert or lab signal carries those factors, so the UI can
  explain it without parsing text (AC-031-05, AC-031-06).
- **G-3** Every lab-derived signal carries the recent trajectory of its test
  (AC-031-06).
- **G-4** Every alert signal says how long it has been active and how often it
  recurred recently (AC-031-07).
- **G-5** Nothing that exists today changes. Labels, details, alert dedupe and
  auto-resolve, `/stats` and `/bootstrap` shapes all stay as they are
  (AC-031-04, AC-031-09).
- **G-6** The dashboard shows proportion, reason, trajectory and recurrence
  visually, readable at 320px and in both themes (§7 B-7..B-12, Vitest and
  Playwright).

## 4. Non-Goals

- **NG-1** No percentage confidence score per alert (§2, ADR-019).
- **NG-2** No clinician feedback loop ("actioned / false positive") and no
  false-positive-rate metrics. Both need a new persisted outcome field and
  real usage to mean anything. That is the next story.
- **NG-3** No patient × test heatmap and no 7-day count sparklines. The
  heatmap is a follow-up. Count sparklines need a persisted daily snapshot.
- **NG-4** No change to which thresholds fire, their severities, or the
  English `label`/`detail` strings. `alerts.py` de-duplicates on
  `(category, title)` (`src/sephiroth/safety/alerts.py:47-53`) and
  auto-resolves on the label (`:92`).
- **NG-5** No schema migration, and no `Alert.rule_key` model column. Factors
  for an alert are recomputed from the patient's current flags.
- **NG-6** No charting dependency.

## 5. Definitions

- **Factor**: one measured input of a firing rule, as
  `{test, value, comparator, threshold, unit}`.
- **Rule code**: a stable, lowercase, snake_case identifier of a rule.
  Examples: `hyperkalemia`, `hypertensive_range`, `drug_interaction`. It is
  the translation key the frontend uses, and is independent of the English
  label.
- **Trend**: up to the last 5 plausible readings of a test for one patient,
  oldest first.
- **Recurrence window**: the 30 days before now.

## 6. Contracts

### 6.1 Types

**Risk flag** (dict returned by `assess_patient_risk`). New fields are marked (new):

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `source` | `"lab"` \| `"drug"` | yes | — | unchanged |
| `label` | str | yes | — | unchanged (English, dedupe key) |
| `severity` | `"high"` \| `"medium"` | yes | — | unchanged |
| `detail` | str | yes | — | unchanged |
| `rule_code` (new) | str | yes | — | §5; unique per `(source, label)` family |
| `factors` (new) | list[Factor] | yes | `[]` | lab flag: ≥1; BP flag: 2 (systolic, diastolic); drug flag: `[]` |
| `drugs` (new) | list[str] | drug flags only | — | the interacting pair, as `find_interactions` returns it |

**Factor**:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `test` | str | yes | — | lowercase test key (`potassium`, `bp_systolic`, …) |
| `value` | float | yes | — | the measured value that fired |
| `comparator` | `">"` \| `"<"` \| `"≥"` | yes | — | the direction of the rule |
| `threshold` | float | yes | — | the cut-off the rule compares against |
| `unit` | str | yes | `""` | display unit (`mEq/L`, `%`, `mmHg`, …) |

**Dashboard action item** (`/api/dashboard/action-items`, inside `groups[].items[]`). New fields only; all existing fields are unchanged:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `rule_code` | str \| null | yes | `null` | set when the signal maps to a currently firing flag |
| `factors` | list[Factor] \| null | yes | `null` | same source as `rule_code` |
| `trend` | list[`{value: float, taken_at: str}`] \| null | yes | `null` | ≤5 entries, ascending `taken_at`, plausible values only |
| `recurrence` | `{active_since: str, prior_count: int}` \| null | yes | `null` | alert items only; `prior_count` ≥ 0 |

### 6.2 Interfaces

Module `src/sephiroth/safety/risk.py`:
- `LabRule` gains `code: str`, `comparator: str`, `threshold: float` and
  `unit: str`.
- `LabRule.flag(value)` adds `rule_code` and `factors`.
- The `(predicate, rule)` tuple shape of `LAB_RULES` is unchanged, so
  `lab_value_abnormality` is untouched.
- The BP flag and interaction flags add their new fields in place.
- New pure helper:

```python
def rule_factors(test_name: str, value: float) -> Optional[Dict[str, Any]]:
    """{rule_code, factors} for the highest-severity LAB_RULES rule `value`
    triggers for `test_name`, or None when none fires."""
```

Module `platform/api/routers/dashboard.py`, `_dashboard_action_items` (no new route):

| Category | `rule_code`/`factors` from | `trend` from | `recurrence` |
|---|---|---|---|
| `alert` (source `risk_engine`) | the patient's current flag whose `label == alert.title`; `null` if it no longer fires | the factor test's history, if it is a lab test | `{active_since: created_at, prior_count}` |
| `alert` (other source) | `null` | `null` | same as above |
| `lab` | `rule_factors(test_name, value)`; BP pairs use the BP rule | that test's history | `null` |
| `deteriorating` | `null` | `test_name`'s history | `null` |
| `interaction` | the matching drug flag (`rule_code: drug_interaction`, `factors: []`) | `null` | `null` |
| other categories | `null` | `null` | `null` |

`prior_count` counts alerts of the same patient and `title` whose status is
`resolved` and whose `resolved_at` falls inside the recurrence window. The
active alert itself is excluded.

Frontend (not a wire contract; listed for traceability):
- `platform/frontend/components/dashboard/risk-distribution.tsx` (new)
- `platform/frontend/components/dashboard/range-bar.tsx` (new)
- `platform/frontend/components/dashboard/mini-trend.tsx` (new). It extracts
  the SVG polyline logic from `lab-trend-card.tsx` into a shared component,
  so both views draw trends one way.
- `platform/frontend/components/action-items-list.tsx` (signal rows enriched)
- `platform/frontend/app/dashboard/page.tsx` (distribution bar, two-column layout)
- `platform/frontend/lib/api.ts` (types)

### 6.3 State machine

`N/A`: read-only enrichment; the alert lifecycle is unchanged.

### 6.4 Errors

- A signal whose rule can no longer be resolved (the flag stopped firing, or
  an unknown test) gets `null` enrichment fields. It is still listed, and the
  endpoint never fails because of it.
- An implausible reading never appears in `trend` or `factors`
  (`is_physiologically_plausible`, `SF068`).

### 6.5 Configuration

`N/A`. The trend length (5) and the recurrence window (30 days) are module
constants, not settings.

## 7. Behaviour

- **B-1** `factors[].threshold` and `comparator` MUST be the values the rule's
  predicate actually uses. The predicate and the declared threshold MUST
  NOT drift. Every `LAB_RULES` entry is asserted by a test.
- **B-2** A range rule (e.g. BMI `30 ≤ v < 40`) MUST declare its lower bound as
  `threshold` with comparator `≥`. The upper bound belongs to the next rule
  in the same list.
- **B-3** The BP flag MUST carry both factors (`bp_systolic ≥ 160`,
  `bp_diastolic ≥ 100`), whichever one fired, so the UI can show the pair.
- **B-4** `rule_code`, `factors` and `drugs` MUST be additive. Every existing key
  and value of a flag MUST stay identical, including `label` and `detail`.
- **B-5** `trend` MUST contain only plausible readings, oldest first, at most 5.
  If fewer than 2 remain, it MUST still be returned (the UI decides not to
  draw a line), or be `null` if there are none.
- **B-6** `recurrence.active_since` MUST equal the alert's `created_at`, in the
  same naive-UTC ISO form as `occurred_at` (`SF069`).
- **B-7** The risk-distribution bar MUST show each segment's count as visible
  text next to its colour, and MUST render an empty-state message when all
  counts are zero.
- **B-8** The range bar MUST mark the threshold and the value, and state them in
  text ("6.8 mEq/L · umbral > 5.5"). Colour alone MUST NOT carry the meaning.
- **B-9** The mini trend MUST NOT draw with fewer than 2 points, and MUST expose
  an accessible label describing first and last values.
- **B-10** The recurrence chip MUST read "activa hace X" (relative, via
  `lib/relative-time.ts`) and add "↻ N" only when `prior_count > 0`.
- **B-11** The clinical explanation MUST come from `risk.explain.<rule_code>` in
  both dictionaries. An unknown code MUST show nothing rather than a raw key.
  Drug interactions reuse the existing `clinical.interaction` phrasing.
- **B-12** Layout MUST be one column below `lg:` and two columns (action items
  wide, critical patients narrow) from `lg:` up. Everything MUST work at 320px
  with no horizontal page overflow and meet the 44px touch-target rule
  (`platform/frontend/CLAUDE.md`). Colours MUST come from the existing
  tokens (`danger`/`warning`/`success`/`primary`). The `sephiroth` gradient is
  reserved for AI content.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-031-01 | For every `LAB_RULES` entry, a value that fires it yields a flag whose `rule_code` is that rule's code and whose single factor has that test, the value, and the rule's declared comparator, threshold and unit | §6.1, B-1, B-2 | `tests/test_risk_explainability.py` |
| AC-031-02 | A hypertensive BP yields `rule_code == "hypertensive_range"` with two factors: `bp_systolic ≥ 160` and `bp_diastolic ≥ 100`, carrying the measured values | B-3 | `tests/test_risk_explainability.py` |
| AC-031-03 | A drug-interaction flag has `rule_code == "drug_interaction"`, `factors == []` and `drugs` equal to the interacting pair | §6.1 | `tests/test_risk_explainability.py` |
| AC-031-04 | Adding the new fields changes no existing flag key or value: `label`, `detail`, `severity` and `source` are byte-identical to before for every rule | B-4, NG-4 | `tests/test_risk_explainability.py` |
| AC-031-05 | A `risk_engine` alert item carries the `rule_code`/`factors` of the patient's currently firing flag with the same label; when that flag no longer fires, the item is still listed with `rule_code`/`factors` `null` | §6.2, §6.4 | `tests/test_dashboard_explainability.py` |
| AC-031-06 | A critical lab item carries `rule_factors` for its value and a `trend` of at most 5 plausible readings of that test, oldest first. An implausible reading is excluded from `trend` | §6.2, B-5 | `tests/test_dashboard_explainability.py` |
| AC-031-07 | An alert item's `recurrence.active_since` equals its `created_at`, and `prior_count` counts only resolved alerts of the same patient and title resolved within the last 30 days | §6.2, B-6 | `tests/test_dashboard_explainability.py` |
| AC-031-08 | Items with nothing to explain (e.g. `followup`, `approval`) have `rule_code`, `factors`, `trend` and `recurrence` all `null`, and an `interaction` item has `rule_code == "drug_interaction"` and `trend` `null` | §6.2 | `tests/test_dashboard_explainability.py` |
| AC-031-09 | `/stats` and `/bootstrap` keep their existing shapes | G-5, NG-4 | `tests/test_dashboard_explainability.py` |

The UI behaviour (B-7..B-12) is verified by the component and E2E tests in
§9. It carries no AC ids, because `scripts/docs_check.py` scans only
`tests/**/*.py`.

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Unit (rules) | AC-031-01..04; predicate/threshold agreement for every rule | `tests/test_risk_explainability.py` (new) |
| API | AC-031-05..09 against the SQLite test DB | `tests/test_dashboard_explainability.py` (new) |
| Regression | Existing labels, alert dedupe and auto-resolve, action-item shape | `tests/test_risk_engine.py`, `tests/test_dashboard_endpoints.py`, `tests/test_alert_lifecycle_api.py` |
| Component | Distribution bar counts and empty state; range bar text and marker; mini trend <2 points and aria label; recurrence chip; explanation fallback | `platform/frontend/components/__tests__/*.test.tsx` (new and updated) |
| E2E | `/dashboard` with mocked enriched items: no overflow at 320px, 44px touch targets | `platform/frontend/e2e/responsive.spec.ts`, `e2e/fixtures/mock-api.ts` |

## 10. Migration & Compatibility

- There is no schema or data migration. Flags and action items only gain
  keys. Existing consumers ignore unknown keys; `RiskFlag` in
  `platform/frontend/lib/api.ts` gains optional fields.
- `LabRule` gains constructor fields. Its only constructor call sites are the
  `LAB_RULES` literals in `risk.py`, so no other code changes.
- The patient detail page's Risk Flags card is unaffected. It may adopt
  `factors` later.

## 11. Risks & Open Questions

| # | Risk / question | Resolution / ADR |
|---|---|---|
| 1 | A rule's declared threshold drifts from its lambda predicate | B-1: AC-031-01 exercises every rule at, below and above its threshold |
| 2 | Recomputing an alert's factors from current data can differ from the value when the alert was raised | Intended: the dashboard answers "why is this still firing now". A non-firing flag yields `null` rather than stale factors (§6.4) |
| 3 | Richer rows lengthen the list on phones | Enrichment renders compactly below the signal text; range bar and trend share one line from `sm:` up and stack below it (B-12) |
| 4 | No persisted rule identity on alerts (`rule_key` exists in a migration but not in the model) | Out of scope (NG-5). Matching by `title` is exact today because titles are generated from the same labels |

## 12. References

- [ADR-019](../08-decisions/ADR-019-dashboard-explainability-visuals.md)
- [SPEC-000](SPEC-000-spec-process.md): lifecycle and gates
- `docs/dev-log/2026-09-26.md`: `SF068`/`SF069`, earlier priorities of the same review

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-09-26 | Initial draft (SF070) |
| 0.1.0 | 2026-09-26 | Approved (SF070) — human review of the draft, including read-time factor recomputation (a flag that stopped firing yields `null` factors) and no confidence percentage, before writing tests |
