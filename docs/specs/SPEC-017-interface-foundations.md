---
id: SPEC-017
title: Interface Foundations
phase: 15
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-000]
adrs: []
features: [F-072, F-073, F-074, F-075, F-076]
diagrams: []
---

# SPEC-017 — Interface Foundations

## 1. Summary

The overlay, list and navigation primitives every later phase builds on, plus
the CI steps that keep them honest: a portal, a focus trap, a drawer and dialog
built on both, a single component that renders a list as either a table or a
card stack, a mobile bottom bar, and `tsc --noEmit` / `eslint` as blocking CI
steps.

No new product capability. This phase exists first because everything after it
ships a screen, and shipping screens onto a shell that has no mobile navigation
and no gate on type errors means building each of them twice.

## 2. Motivation

Three concrete defects, all of them invisible to someone developing on a laptop
with a mouse:

1. **The application has no navigation below `md`.** `components/sidebar.tsx:86`
   is `hidden … md:flex` and nothing replaces it. On a phone a clinician can
   reach exactly the page they landed on.
2. **`Sheet` is modal only to a mouse.** `components/ui/sheet.tsx` rendered in
   normal DOM order with no portal and no focus trap — its docstring recorded
   this as acceptable "since Next's client tree already renders it above
   everything else". That is not true in this app: `.glass-surface`
   (`app/globals.css`) uses `backdrop-blur` and the sidebar is `sticky`, both of
   which establish containing blocks that clip an overlay regardless of
   `z-index`. Without a trap, Tab leaves the drawer for the page behind it.
3. **CI does not gate the frontend.** `.github/workflows/ci.yml`'s `frontend`
   job ran `vitest` and `next build` only. A `lint` script existed in
   `package.json` and nothing called it; ESLint was not even installed. Type
   errors surfaced only through the build, and only in code the build could
   reach.

`app/patients/page.tsx` was the concrete case for the list primitive: a
`<table className="w-full min-w-[640px]">`, which on a 375px screen is a
horizontal scrollbar most people never find.

## 3. Goals

- **G-1** Every destination the sidebar offers is reachable on a phone.
- **G-2** An open overlay holds keyboard focus and returns it on close.
- **G-3** An overlay is not clipped by the layout it was opened from.
- **G-4** A list column is declared once and appears in both the table and the
  card shape.
- **G-5** A type error or a new lint warning fails CI as its own named step.

## 4. Non-Goals

- **NG-1** No navigation restructuring. The destinations, their grouping, and
  which are top-level are unchanged here; SPEC-019 does that.
- **NG-2** No headless UI library. Radix was dropped deliberately
  (`components/magicui/bento-grid.tsx:10`) and is not reintroduced — see §11.
- **NG-3** No visual regression testing. See §11 risk 2.
- **NG-4** No PWA, service worker, or install prompt; SPEC-025.
- **NG-5** No responsive pass over every page. Only `/patients` and
  `/patients/[id]` are converted here, because they are the two that survive
  SPEC-019's route restructure unchanged. Converting the rest first would mean
  converting them twice.

## 5. Definitions

- **Primary column** — a `DataList` column marked `primary: true`, rendered as
  the card headline on a phone rather than as a labelled line.
- **Overflow destination** — a navigation item without `mobile: true`, reachable
  on a phone through the drawer rather than the bottom bar.

## 6. Contracts

### 6.1 Types

`platform/frontend/lib/nav.ts`:

```ts
export interface NavItem {
  href: string;
  id: string;
  icon: LucideIcon;
  mobile?: boolean;
}

export interface NavGroup {
  groupId: string | null;
  items: NavItem[];
}
```

`platform/frontend/components/ui/data-list.tsx`:

```ts
export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  primary?: boolean;
  desktopOnly?: boolean;
  className?: string;
}
```

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `NavItem.mobile` | bool | no | `false` | at most 4 per role; the 5th bar slot is the drawer trigger |
| `Column.primary` | bool | no | `false` | when no column sets it, the first column is treated as primary |
| `Column.desktopOnly` | bool | no | `false` | dropped from the card shape, never merely hidden |

### 6.2 Interfaces

```ts
// lib/hooks/use-focus-trap.ts
export function useFocusTrap(container: HTMLElement | null, active: boolean): void

// lib/nav.ts
export function navFor(role: string | undefined): NavGroup[]
export function flatNav(groups: NavGroup[]): NavItem[]
export function isActive(pathname: string, href: string, allHrefs: string[]): boolean

// components/ui/toast.tsx
show(message: string, kind?: "success" | "error",
     options?: { action?: { label: string; onClick: () => void }; durationMs?: number }): void
```

`useFocusTrap` takes the element, **not** a `RefObject`. `Portal` mounts its
children one render after its parent, so a ref's `.current` is invisible to the
dependency array: the effect would run once against `null` and never again, and
the trap would silently do nothing. Callers hold the node in state via a
callback ref.

`show`'s first two parameters are unchanged, so every existing call site keeps
working.

### 6.3 State machine

`N/A` — these are presentational primitives; no persisted state transitions.

### 6.4 Errors

`N/A` — no new exception types. `useToast` continues to throw when used outside
`ToastProvider`.

### 6.5 Configuration

`N/A` — no runtime settings. Build configuration only: `.eslintrc.json`
extending `next/core-web-vitals`, and the `typecheck`/`lint` scripts in
`package.json` (`lint` runs with `--max-warnings=0`).

## 7. Behaviour

- **B-1** `Portal` MUST render `null` on the server and on its first client
  pass, so server and client markup match.
- **B-2** An overlay using `useFocusTrap` MUST move focus into itself on open,
  cycle Tab and Shift+Tab within itself, and restore focus to the previously
  focused element on close.
- **B-3** The focus trap MUST pull focus back inside when Tab is pressed while
  focus sits outside the container.
- **B-4** `useFocusTrap` MUST NOT use `offsetParent` or `getClientRects` to
  decide visibility: jsdom performs no layout and reports every element
  invisible, so a trap filtered that way cannot be proven to work by any test.
- **B-5** The mobile bar MUST expose every `mobile: true` destination, and the
  drawer MUST expose every other destination for that role.
- **B-6** The current destination MUST be marked with `aria-current="page"`,
  resolved by longest prefix so `/patients/P001` marks `/patients` and only
  `/patients`.
- **B-7** The drawer MUST close on navigation.
- **B-8** `DataList` MUST render both shapes at every width and let CSS choose,
  so no layout shifts on hydration.
- **B-9** `DataList` MUST NOT render an empty table: with no items it renders
  the empty message, and while loading it renders a busy placeholder.
- **B-10** The app shell MUST reserve space for the fixed bottom bar.
- **B-11** No page may contain a raw `<table>`; lists go through `DataList`.
- **B-12** No component may set a fixed width above 375px without a recorded
  exception.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-017-01 | The overlay renders into `document.body`, not into its parent container | B-1, G-3 | `platform/frontend/components/__tests__/sheet.test.tsx` |
| AC-017-02 | Focus moves into the panel on open and returns to the opener on close | B-2 | `platform/frontend/components/__tests__/sheet.test.tsx` |
| AC-017-03 | Tab from the last control wraps to the first, and Shift+Tab from the first wraps to the last | B-2 | `platform/frontend/components/__tests__/sheet.test.tsx` |
| AC-017-04 | Tab pressed while focus is outside the panel returns focus inside it | B-3 | `platform/frontend/components/__tests__/sheet.test.tsx` |
| AC-017-05 | Page scroll is locked while an overlay is open and released on close | B-2 | `platform/frontend/components/__tests__/sheet.test.tsx` |
| AC-017-06 | Every sidebar destination is reachable from the mobile bar or its drawer | B-5, G-1 | `platform/frontend/components/__tests__/mobile-nav.test.tsx` |
| AC-017-07 | A nested route marks its parent destination as current, and only it | B-6 | `platform/frontend/components/__tests__/mobile-nav.test.tsx` |
| AC-017-08 | The drawer opens with the overflow destinations and closes on Escape | B-5, B-7 | `platform/frontend/components/__tests__/mobile-nav.test.tsx` |
| AC-017-09 | Every column appears in the table shape; `desktopOnly` columns are absent from the card shape | B-8, G-4 | `platform/frontend/components/__tests__/data-list.test.tsx` |
| AC-017-10 | Every non-primary card value carries its column header as a label | G-4 | `platform/frontend/components/__tests__/data-list.test.tsx` |
| AC-017-11 | Loading renders a busy placeholder and no table; empty renders the empty message and no table | B-9 | `platform/frontend/components/__tests__/data-list.test.tsx` |
| AC-017-12 | No file outside `data-list.tsx` contains a raw `<table>` | B-11 | `platform/frontend/lib/__tests__/responsive.test.ts` |
| AC-017-13 | No file sets a fixed width above 375px without a recorded exception | B-12 | `platform/frontend/lib/__tests__/responsive.test.ts` |
| AC-017-14 | The app shell reserves space for the fixed bottom bar | B-10 | `platform/frontend/lib/__tests__/responsive.test.ts` |

The AC ids above are referenced from the test files themselves, which is what
`scripts/docs_check.py` verifies. Note these are vitest suites rather than
pytest ones — the docs gate greps `tests/` for the id, so each id is also
recorded in `tests/test_docs_gates.py`'s frontend-AC manifest.

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Component | portal placement, focus trap, scroll lock, Escape/scrim | `components/__tests__/sheet.test.tsx` |
| Component | bar/drawer split, active marking, reachability | `components/__tests__/mobile-nav.test.tsx` |
| Component | both shapes from one column set, loading/empty | `components/__tests__/data-list.test.tsx` |
| Lint-by-test | raw tables, fixed widths, bottom-bar clearance | `lib/__tests__/responsive.test.ts` |
| CI | type errors, lint warnings | `.github/workflows/ci.yml` job `frontend` |

## 10. Migration & Compatibility

Additive. `Sheet`'s props gain an optional `side`, defaulting to the existing
right-side behaviour, so its three current callers are unchanged.
`useToast`'s first two parameters are unchanged. `sidebar.tsx` keeps its markup
and only sources its config from `lib/nav.ts`.

`/patients` moves from a raw table to `DataList`. `/patients/[id]` gains a
skeleton loading state and a wrapping action group. No other page changes.

Nothing is shimmed and nothing is scheduled for deletion.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Hand-rolling dialog/menu/tabs primitives repeats work a library solves, and accessibility bugs here are silent | Accepted, with an escape hatch: reintroducing Radix contradicts a documented decision and drags 6–8 packages plus a restyle of `.btn-*`, while the genuinely hard parts (portal, focus trap) are ~60 lines and are now tested. If focus bugs recur across two rounds, adopt `@radix-ui/react-dialog` alone — one unstyled package — not shadcn wholesale |
| 2 | Two lint-by-test rules and a manual checklist are not visual regression testing | Accepted. No e2e harness exists, and a visual baseline over 4 widths × ~12 pages is a maintenance liability with no owner. Revisit only when a real e2e need (login, booking) appears |
| 3 | `DataList` renders both shapes at every width, doubling the DOM for a list | Accepted: it is what buys "no layout shift on hydration" and "the two shapes cannot drift". Revisit if a list ever needs virtualisation, which none does |
| 4 | `DropdownMenu` is not portalled, so it can be clipped inside an overflow container | Accepted and bounded: a dropdown must stay anchored to its trigger, and re-implementing positioning against scroll/resize buys nothing at this size. The phone path opens a bottom `Sheet` instead, which is the better shape for a thumb regardless |
| 5 | `/schedule`'s week grid keeps a `min-w-[900px]` | Recorded as an exception in the lint-by-test. It sits inside its own horizontal scroller; the phone gets a day view in SPEC-019 |
| 6 | Two `<img>` elements keep an eslint-disable rather than moving to `next/image` | One is an object-URL preview `next/image` cannot optimise. The other is the landing gallery, where the change is a layout change on a page nobody can visually verify in CI; it belongs with the landing rewrite (SPEC-026) |

## 12. References

- `docs/00-migration-charter.md` — phase rules and the coverage gate.
- WCAG 2.5.5 / Apple HIG — the 44px touch-target figure `.tap` encodes.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version; implemented in phase 15 |
