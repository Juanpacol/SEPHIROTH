# Frontend conventions

Next.js 14 App Router, Tailwind v3, TypeScript strict. Read the repo root
`CLAUDE.md` first for the product and the design tokens; this file covers the
rules that are specific to writing UI here.

## Responsive

The app is used on phones. Every route has to work at 320px, and CI enforces it
(`e2e/responsive.spec.ts`, four viewport projects).

**CSS-first.** If both shapes of a thing can sit in the DOM and CSS can pick
which one shows, do it with CSS (`md:hidden` / `hidden md:block`) rather than
branching in JavaScript. No layout shift on hydration, no client/server
mismatch, and the two shapes cannot drift apart — the reasoning is spelled out
in `components/ui/data-list.tsx`. `lib/hooks/use-media-query.ts` exists for the
cases where JavaScript has to branch on *logic*, not presentation: computing
positions (`components/landing/masonry.tsx`), or genuinely not mounting an
expensive subtree. Reach for it last.

**Patterns already solved — reuse, don't rebuild:**

| Need | Use |
|---|---|
| A list of records | `components/ui/data-list.tsx` — one column declaration renders a table from `md:` up and cards below it |
| Master-detail | The dual shell in `app/approvals/page.tsx`: the detail inline under `hidden md:block`, and again inside `<Sheet side="bottom">` under `md:hidden` |
| A drawer or action sheet | `components/ui/sheet.tsx` (`side="right" \| "left" \| "bottom"`) — portal, scrim, Escape, focus trap |
| A confirm | `components/ui/dialog.tsx` |
| A wide table or timetable | Keep it wide inside its own `overflow-x-auto`, and give phones a different view — `/schedule` pairs `week-grid.tsx` with `day-strip.tsx` + `day-agenda.tsx` |

**Rules that earn their keep:**

- Every tappable control is at least 44px in one dimension. Add `.tap` — a
  bare 12px text link is not a touch target. `data-tap-exempt` on an ancestor
  opts a genuinely inline target out, and every use has to justify itself.
- A grid needs an explicit `grid-cols-1` (or `minmax(0, 1fr)` tracks). A bare
  `grid gap-4 md:grid-cols-2` leaves the implicit column at `auto`, whose floor
  is min-content — one textarea then pushes the whole grid past the viewport.
- `dvh`, never `vh`. Safari measures `vh` against the viewport with the URL bar
  expanded, so `90vh` hangs off the bottom of an iPhone.
- A flex child that should truncate needs `min-w-0` on itself, not just
  `truncate` on the text.
- Anything pinned to the bottom edge needs `.safe-bottom`; anything the tab bar
  would cover needs `.pb-tabbar` on the page's flex **column** (a margin on the
  last child overflows instead of moving it — see the comment in `globals.css`).
- Never hide content behind `hover:` alone. There is no hover state on a touch
  screen, so the content is both invisible and unreachable.
- No `window.confirm` / `alert` / `prompt`. They block the main thread, cannot
  be translated or styled, and on a phone throw the user out of the app
  entirely. Use `components/ui/dialog.tsx` — `/schedule` shows the shape: the
  child raises the intent, the page owns one dialog for both views.

**Known limitation:** iOS shrinks the *visual* viewport for the on-screen
keyboard but leaves the *layout* viewport alone, so `position: fixed` bottom
bars can end up behind it. `dvh` plus scrolling the focused field into view (see
`copilot-panel.tsx`) is as far as WebKit lets us go; there is no VirtualKeyboard
API there.

## Navigation

`lib/nav.ts` is the single source of destinations. The desktop sidebar, the
mobile tab bar and the mobile drawer all read from it; `primary: true` promotes
an item to the tab bar (five maximum). Adding a route means adding it there, not
in three components.

## i18n

All copy goes through `useLanguage()` and lives in
`lib/i18n/dictionaries.{en,es}.ts`. Both dictionaries, always —
`lib/__tests__/i18n.test.ts` fails the build over a key present in only one.

## Tests

- `npm run test` — Vitest, jsdom. Note that `DataList` renders *both* shapes at
  every width and jsdom applies no CSS, so scope queries with
  `within(screen.getByRole("table"))` / `getByRole("list")` or you will get
  "found multiple elements".
- `npm run test:e2e` — Playwright: overflow and touch-target assertions over
  every route in `e2e/responsive.spec.ts`'s `ROUTES`, plus `e2e/shell.spec.ts`
  for the navigation shell. A new route joins `ROUTES` and gets its endpoints
  added to `e2e/fixtures/mock-api.ts` — **without the mock the page renders its
  empty state and the test passes having checked nothing.**
- `npm run lint` — `--max-warnings=0`. Keep it there.

Fixture timestamps in `e2e/fixtures/mock-api.ts` are naive (no trailing `Z`) and
relative to today, and both matter: the app re-appends a `Z`
(`components/schedule/time.ts`), and /schedule only queries the current week —
get either wrong and the page renders empty while the assertions still pass.
