---
id: SPEC-019
title: Work Center and Information Architecture
phase: 17
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-017, SPEC-018]
adrs: []
features: [F-082, F-083, F-084]
diagrams: []
---

# SPEC-019 — Work Center and Information Architecture

## 1. Summary

The navigation is reorganised around what a clinician does rather than how the
system is built: a flat list in the order a day runs, a `/work` home that leads
with today instead of with panel statistics, and two list pages over data that
already existed and was only reachable one patient at a time.

Every old URL still resolves. Nothing is deleted from the product — three
destinations move out of the primary navigation and into the flow where they
are used.

## 2. Motivation

The sidebar listed the system's parts. The group labels were the tell —
"Clinical" and "Intelligence" (`components/sidebar.tsx:32,41`) describe an
architecture, and the second group is the proof: `/imaging`, `/evidence` and
`/agents` were top-level destinations because they are interesting features,
not because anyone begins a day by opening them.

Three concrete symptoms:

1. **`/dashboard` led with counts nobody acts on.** Four stat cards: critical,
   moderate, stable, max priority score. Only the first is a call to action;
   nobody opens the app and does something because the stable count moved.
2. **`bootstrap.agenda` was fetched and discarded.** `GET /api/dashboard/bootstrap`
   has always returned today's appointments, and `app/dashboard/page.tsx` never
   rendered them, so the first question of the day — who am I seeing next —
   required a second page.
3. **Working endpoints had no page.** `GET /api/results/shares` and
   `GET /api/followups` were only reachable from inside one patient's chart,
   which makes "what have I shared that nobody has opened" and "who is on a
   plan right now" questions you can only answer by opening patients one by
   one.

Plus dead weight: eleven dashboard endpoints in `lib/api.ts` that nothing
rendered, their interfaces, and the ~80 i18n keys that went with them.

## 3. Goals

- **G-1** The primary navigation names work, not subsystems, and is flat.
- **G-2** Every URL that worked before still works.
- **G-3** `/work` opens on what is happening today.
- **G-4** Data the backend already serves has a page.
- **G-5** Surface nothing renders is deleted, not kept in case.

## 4. Non-Goals

- **NG-1** No `middleware.ts`. The JWT lives in `localStorage` and is invisible
  to middleware; moving it to a cookie is an explicit non-goal (CLAUDE.md #22).
  Renames are server-component `redirect()` stubs, the pattern `/copilot`
  already used.
- **NG-2** No feature is removed. `/evidence`, `/imaging` and `/agents` keep
  working; only their place in the navigation changes.
- **NG-3** No `/consultations` or `/communications` page yet — the first needs
  the encounter model (SPEC-023) to be worth opening, and the second would be a
  notification list with no channel behind it until SPEC-025.
- **NG-4** The i18n dictionaries are not split into modules. At ~670 keys after
  the deletions the single file is still navigable; splitting is a change with
  a merge-conflict benefit and a duplicate-key risk, and it can wait for the
  phase that actually doubles the key count.
- **NG-5** No admin metrics page. The three admin-flavoured dashboard endpoints
  are deleted with the rest; re-adding them behind `/admin/system` is future
  work, and keeping dead client code alive in the meantime helps nobody.

## 5. Definitions

- **Redirect stub** — a server component whose whole body is `redirect(...)`,
  left at an old route.
- **Demoted destination** — a page that keeps its URL but leaves the primary
  navigation, reached from the flow that needs it.

## 6. Contracts

### 6.1 Types

`platform/frontend/lib/nav.ts` — `NavItem`/`NavGroup` unchanged from SPEC-017.
`CLINICIAN_NAV` becomes a single group with `groupId: null`.

`platform/frontend/lib/api.ts` — `ResultShare` gains `patient_id: string`,
mirroring the additive field added to `_share_out` in
`platform/api/routers/results.py`. A clinician-facing list shows rows from many
patients at once and cannot name them otherwise; on the patient side it tells
them nothing they did not send.

### 6.2 Interfaces

```ts
// lib/language.tsx
t(key: string, vars?: Record<string, string | number>): string
```

`vars` is optional, so every existing call site is unchanged. It exists
because several already hand-rolled it — `ActionItemsList` does
`.replace("{test}", …)` five times — and a convention repeated by hand drifts.

### 6.3 State machine

`N/A` — no persisted state transitions.

### 6.4 Errors

`N/A` — no new error types.

### 6.5 Configuration

`N/A` — no runtime settings.

## 7. Behaviour

- **B-1** Every renamed route MUST keep resolving, via a `redirect()` stub.
- **B-2** Every redirect stub MUST be classified as a clinician route.
  Otherwise `AuthGuard` bounces a signed-in clinician before the redirect runs,
  and an old bookmark becomes a logout.
- **B-3** The clinician navigation MUST be flat.
- **B-4** Every navigation destination MUST have a page behind it and MUST pass
  the auth guard.
- **B-5** A demoted destination MUST keep its route and its page.
- **B-6** `/work` MUST render today's agenda from the payload it already
  fetches.
- **B-7** The agenda card MUST NOT display a negative countdown; an appointment
  whose start has passed reads as under way.
- **B-8** `t()` MUST substitute `{name}` placeholders when given `vars`, and
  MUST behave exactly as before when not.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-019-01 | Every renamed route redirects to its new home | B-1 | `platform/frontend/lib/__tests__/route-restructure.test.ts` |
| AC-019-02 | Every redirect stub is a clinician route, so the guard lets it through | B-2 | `platform/frontend/lib/__tests__/route-restructure.test.ts` |
| AC-019-03 | The work center renders the agenda the dashboard used to discard | B-6 | `platform/frontend/components/__tests__/agenda-today-card.test.tsx` |
| AC-019-04 | The countdown interpolates through `t(key, vars)` and never runs negative | B-7, B-8 | `platform/frontend/components/__tests__/agenda-today-card.test.tsx` |

Registered in `tests/test_docs_gates.py::FRONTEND_ACCEPTANCE_CRITERIA`, per the
convention SPEC-017 §8 established.

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Routing | redirects, guard classification, nav/page correspondence | `lib/__tests__/route-restructure.test.ts` |
| Component | agenda rendering, countdown, empty and overflow states | `components/__tests__/agenda-today-card.test.tsx` |
| Regression | the moved settings section still works | `components/settings/__tests__/automation-section.test.tsx` |
| Guardrails | the schedule grid's width exception follows the rename | `lib/__tests__/responsive.test.ts` |

## 10. Migration & Compatibility

Six redirect stubs: `/dashboard`→`/work`, `/schedule`→`/agenda`,
`/agents`→`/admin/ai`, `/profile` and `/preferences`→`/settings`, and
`/copilot`→`/work` (repointed).

`homeFor()`, the pre-paint auth gate and the sidebar's home link all move to
`/work` together — they are the one place "which role goes where" is decided
(CLAUDE.md #22), so a session whose `localStorage` still says `/dashboard`
lands on the stub and is forwarded.

`_share_out` gains `patient_id`. Additive; the portal ignores it.

Deleted: eleven `lib/api.ts` dashboard endpoints and their interfaces, ~80
orphaned i18n keys, and the non-functional sidebar search box.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Six redirect stubs are six files that exist only to forward | Accepted: each one is four lines and the alternative is a dead bookmark. They can be removed once the URLs have aged out, which is a judgement call about traffic, not about code |
| 2 | Demoting `/evidence`, `/imaging` and `/agents` makes them harder to find before the in-flow entry points exist | Accepted and bounded: all three keep their URLs and are one address-bar away. The in-flow entry points (evidence from an alert, imaging inside the patient page) land with SPEC-023/024 |
| 3 | `/results` and `/followups` fetch the whole patient list to resolve names | Accepted at clinic scale — this is a single-tenant deployment with tens of patients. The alternative is denormalising a name onto two payloads, which is worse the first time somebody renames a patient |
| 4 | The i18n dictionaries are still one file each | See NG-4 |
| 5 | The flat nav is nine items, which is at the upper end of what scans well | Accepted for now: grouping is what was just removed, and re-introducing it after two phases of change would be reorganising before knowing which items people actually use |

## 12. References

- `docs/specs/SPEC-017-interface-foundations.md` — the primitives and the
  frontend-AC convention.
- `docs/specs/SPEC-018-unified-tasks.md` — the inbox this navigation leads to.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version; implemented in phase 17 |
