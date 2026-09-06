---
id: SPEC-021
title: Deterministic Clinical Rules
phase: 19
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-018, SPEC-020]
adrs: []
features: [F-089, F-090]
diagrams: []
---

# SPEC-021 — Deterministic Clinical Rules

## 1. Summary

Gives every risk rule a stable identity separate from its display copy, fixes
the duplication that identity was hiding, separates clinical findings from
administrative ones, and adds two rules that were missing: a medication
matching a recorded allergy, and the same drug listed twice.

Every rule remains a lookup or a comparison. No model is asked anything.

## 2. Motivation

**The duplication was real, but not for the reason previously recorded.**
SPEC-009's audit suggested titles varied by a numeric value; they do not —
`LabRule.label` is a fixed string and the value lives in `detail`. The actual
defect was narrower and worse:

```python
existing_active = await session.scalars(
    select(Alert).where(Alert.patient_id == patient.id, Alert.status == "active")
)
already_open = {(a.category, a.title) for a in existing_active}
```

An alert a clinician had marked **`reviewed`** but not resolved was absent from
that set, so the next sweep filed it again. Before SPEC-020 that surfaced once
per deploy, because `generate_alerts_for_all_patients` only ran at boot. Making
`alert_refresh` genuinely periodic turned it into every six hours — this phase
exists partly because the previous one made an existing bug matter.

Two further problems with keying on `(category, title)`:

- **The key is display copy.** Rewording "Hypokalemia" to "Low potassium" would
  duplicate every open alert of that rule at once.
- **Nothing records which threshold fired.** `Alert.source` was always the
  literal string `"risk_engine"`, so a clinician could not trace a warning back
  to the rule that produced it.

And one queue held everything: "critical potassium" and "nobody confirmed a
booking" sat side by side, which is how the second teaches people to skim past
the first.

## 3. Goals

- **G-1** A rule's identity survives rewording its label.
- **G-2** An alert somebody is already working on is not filed again.
- **G-3** Every warning can name the threshold that produced it.
- **G-4** Clinical and administrative findings are distinguishable.
- **G-5** Two rules that were missing are present.

## 4. Non-Goals

- **NG-1** No LLM anywhere in this path. The model explains and drafts; the
  rule decides.
- **NG-2** No cross-class allergy inference (a cephalosporin for a penicillin
  allergy). That needs a drug-class table this codebase does not have, and
  inventing one here would be guessing at clinical content rather than
  encoding it.
- **NG-3** No alerts for overdue follow-ups, patients without recent control,
  or no-shows. Those already exist as tasks — `task_derivation.py` derives the
  first, SPEC-020's sweep produces the third — and building a second mechanism
  that files the same work twice would be worse than not having it.
- **NG-4** No backfill of `rule_key` onto existing rows. See §10.
- **NG-5** No merging of already-separate alerts. Deduplication prevents new
  duplicates; consolidating historical ones is a data-repair task, not a
  behaviour change.

## 5. Definitions

- **Rule key** — a stable, machine-readable identity for a rule
  (`lab.potassium.high`), decoupled from its label.
- **Kind** — `clinical` (a finding about the patient) or `administrative` (a
  finding about the process).

## 6. Contracts

### 6.1 Types

`src/sephiroth/safety/risk.py`:

```python
@dataclass
class LabRule:
    key: str  # stable identity, e.g. "lab.potassium.high"
    label: str  # display copy
    severity: str  # "high" | "medium"
    detail: str  # formatted with the observed value
    source: str = ""  # the threshold, e.g. "K+ > 5.5 mEq/L"
```

Every flag dict now carries `rule_key`, `rule_source` and `kind` alongside the
existing `source`, `label`, `severity` and `detail`.

`data/schemas/__init__.py::Alert` gains:

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `rule_key` | String(120) | no | null | null only on rows predating this phase |
| `kind` | String(20) | yes | `clinical` | `ck_alert_kind` |

### 6.2 Interfaces

```python
def assess_patient_risk(
    lab_results, medications=None, allergies=None
) -> List[Dict[str, str]]
```

`allergies` is a new third parameter with a default, so every existing
two-argument call site keeps working and simply gets no allergy flags — the
same degrade-quietly posture the rest of the module takes toward missing data.

### 6.3 State machine

`N/A` — the alert lifecycle is unchanged (SPEC-009 §6.3).

### 6.4 Errors

`N/A` — no new exception types. A malformed input (an allergy string too short
to match on, an unparseable lab value) is skipped rather than raised.

### 6.5 Configuration

`N/A` — no runtime settings. Thresholds are code, deliberately: a clinical
cutoff that can be changed without review is a clinical cutoff nobody reviews.

## 7. Behaviour

- **B-1** Every flag MUST carry a non-empty `rule_key`, `rule_source` and
  `kind`.
- **B-2** Rule keys MUST be unique across the rule set.
- **B-3** A rule's key MUST NOT change when the observed value changes.
- **B-4** A drug-pair rule's key MUST be order-independent.
- **B-5** Deduplication MUST compare against every non-`resolved` alert, not
  only `active` ones.
- **B-6** Deduplication MUST key on `rule_key`, falling back to
  `(category, title)` for rows that predate it.
- **B-7** A `resolved` alert whose condition still holds MUST be raisable
  again — resolved means the clinician dealt with it, so a recurrence is new
  information.
- **B-8** `Alert.source` MUST record the threshold that fired, not the engine.
- **B-9** A medication matching a recorded allergy MUST be flagged `high`.
- **B-10** An allergy entry too short to match on MUST be ignored rather than
  matching most of the formulary.
- **B-11** The same active ingredient listed twice MUST be flagged once.
- **B-12** The unconfirmed-appointment alert MUST be `administrative`.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-021-01 | Every rule carries a key, a source and a kind, and keys are unique | B-1, B-2 | `tests/test_clinical_rules.py::TestRuleIdentity` |
| AC-021-02 | A rule's key is stable across values and drug-pair order | B-3, B-4 | `tests/test_clinical_rules.py::TestRuleIdentity` |
| AC-021-03 | A reviewed-but-unresolved alert is not filed again; a resolved one may be | B-5, B-7 | `tests/test_clinical_rules.py::TestAlertsDoNotRepeat` |
| AC-021-04 | An alert records the rule key and the threshold that fired | B-8 | `tests/test_clinical_rules.py::test_the_alert_records_the_rule_and_its_threshold` |
| AC-021-05 | Allergy conflicts and duplicate medications are flagged; near-misses are not | B-9, B-10, B-11 | `tests/test_clinical_rules.py::TestNewRules` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | rule identity, allergy and duplicate matching | `tests/test_clinical_rules.py::TestRuleIdentity`, `TestNewRules` |
| Persistence | deduplication across statuses, legacy rows | `tests/test_clinical_rules.py::TestAlertsDoNotRepeat` |
| Regression | existing risk-engine behaviour unchanged | `tests/test_risk_engine.py` |
| Workflow | the unconfirmed alert is administrative | `tests/test_appointment_reminder_workflow.py` |

## 10. Migration & Compatibility

Revision `d7b3e91c045a`, purely additive: `alerts.rule_key` (nullable),
`alerts.kind` (defaulted), two indexes and a check constraint.

`rule_key` is **deliberately left NULL** on existing rows. The only thing
available to fill it with is the display title those rows already carry, which
would invent identities that were never real — and invent them wrong the moment
a label is reworded. `alerts.py` handles the mixed population directly: a row
with a key dedupes on it, a row without one keeps the old comparison until it
is resolved, at which point the population heals itself.

Written by hand; the local Postgres was unavailable. Not yet executed against a
real database — see §11 risk 1.

`assess_patient_risk` gains a third parameter with a default, so no call site
changes. `Alert.source` now varies per rule instead of always being
`"risk_engine"`; nothing filters on that value.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Neither this revision nor SPEC-020's has run against a real Postgres | Recorded; both are on the verification list. This one is purely additive, so the risk is lower than SPEC-020's backfill |
| 2 | Allergy matching is substring-based and will miss cross-class reactions | Accepted and stated in NG-2. It is a screening rule a clinician reads, not a prescribing decision, and catching "Penicilina V 500mg" from "penicilina" is worth more than the false positives fuzzier matching would add. A drug-class table is the real fix and is not something to invent here |
| 3 | Duplicate-medication detection normalises crudely (strips dose and form) | Same reasoning. Two spellings of one drug being recognised as one is the point; a missed exotic synonym is a missed flag, not a wrong one |
| 4 | An allergy recorded as a brand name will not match a generic prescription | Known gap, same root cause as risk 2 — there is no name-mapping table. Recorded rather than half-solved |
| 5 | `kind` defaults to `clinical`, so a future administrative producer that forgets to set it is silently miscategorised | Accepted: the alternative is a required field that every existing call site must be edited to supply, and `clinical` is the safer default of the two — over-prioritising an administrative item is a smaller harm than burying a clinical one |
| 6 | Thresholds live in code, so changing one needs a deploy | Deliberate. A clinical cutoff that can be edited without review is a clinical cutoff nobody reviews |

## 12. References

- `docs/specs/SPEC-009-automation-substrate.md` — the alert lifecycle.
- `docs/specs/SPEC-020-automation-correctness.md` — made `alert_refresh`
  periodic, which is what turned this duplication from rare into routine.
- `docs/specs/SPEC-018-unified-tasks.md` — where these alerts land as work.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version; implemented in phase 19 |
