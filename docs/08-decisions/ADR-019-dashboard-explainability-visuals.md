# ADR-019 — Dashboard explainability: structured rule factors, hand-rolled visuals, no fake confidence

**Status:** Accepted · **Date:** 2026-09-26 · **Phase:** decided 16 (SPEC-031, pending implementation in `SF070`)

## Context

After fixing data trust (`SF068`) and clarity (`SF069`), the dashboard review
asked for richer visuals. Evaluating a longer list of CDSS ideas against the
data actually available narrowed the choice to what improves the
information a clinician gets *today*: why a signal fired, whether it is
getting worse, whether it is new — plus a visual summary of proportions.

The explanation of every rule-based flag exists only inside an English
format string (`src/sephiroth/safety/risk.py`, e.g.
`"Potassium {value} mEq/L (> 5.5)"`). The frontend has no chart library; its
one chart is a small SVG sparkline in
`platform/frontend/components/patients/lab-trend-card.tsx`.

## Problem

- To draw "value vs threshold" or translate the reason, the frontend would
  have to regex-parse English strings — silently broken by any wording
  change.
- A commonly requested "confidence %" per alert has no honest source: the
  engine is deterministic; a threshold fires or it does not.
- Changing labels to carry structure would re-open every active alert,
  because `alerts.py` de-duplicates on `(category, title)` and auto-resolves
  on the label.

## Decision

1. Add structured, additive fields to every risk flag — `rule_code`,
   `factors: [{test, value, comparator, threshold, unit}]` (and `drugs` for
   interactions) — declared on `LabRule` next to the predicate they describe.
   Labels and details stay byte-identical.
2. Enrich dashboard action items at read time with `rule_code`/`factors`,
   a short `trend` of the triggering test, and `recurrence` (active since,
   prior resolved count in 30 days). No migration, no new table.
3. Draw the new visuals — risk distribution bar, value-vs-threshold range
   bar, mini trend, recurrence chip — as hand-rolled SVG/CSS using existing
   tokens, extracting the existing sparkline into a shared component.
4. Do not show a probability/confidence percentage.

## Rationale

- Structured factors are the single source for the range bar, the translated
  reason and future uses (feedback, heatmap); declaring them beside the
  predicate keeps rule and explanation reviewable together, and a test pins
  them to each other.
- Read-time enrichment cannot drift from source tables and avoids the
  `Alert.rule_key` model/migration drift, which is a separate cleanup.
- The needed shapes are simple; a charting library would add weight and a
  second theming system for no capability the dashboard needs.
- Showing "95% confident" on a threshold rule would erode trust the moment a
  clinician asks what it means.

## Consequences

- `LabRule` carries both a predicate and a declared threshold; they can
  diverge if edited carelessly — mitigated by a test over every rule.
- An alert's factors describe *current* data; if the flag stopped firing,
  the alert shows no factors rather than stale ones.
- (SF072, SPEC-031 1.1.0) The one aggregate chart added later, "what
  dominates today", draws **counts of patients per active rule** from a
  read-time endpoint over the same population as `/stats`: the same
  honest-data rule, with no trends and no predictions. It replaced the
  critical-patients card instead of adding to the page.
- Deferred to follow-up stories: clinician feedback + false-positive rate,
  patient × test heatmap, persisted daily snapshot for count sparklines,
  persisting rule identity on alerts.

## Alternatives rejected

- **Regex-parse `detail` in the frontend** — fragile, cannot compute
  recurrence, keeps the English-only problem.
- **Persist factors on `Alert` rows** — needs a migration and still requires
  current values for the trend; read-time recomputation is enough today.
- **Recharts / visx / Chart.js** — unnecessary dependency and theming layer.
- **Confidence percentage from data completeness** — conflates freshness
  with certainty; freshness is better shown directly (`occurred_at`, trend).
