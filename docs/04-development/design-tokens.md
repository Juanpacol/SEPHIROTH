# Design tokens

The colour, motion and contrast rules every screen builds on. The values live in
`platform/frontend/app/globals.css` (`:root`, `.dark`) and are exposed to Tailwind
in `platform/frontend/tailwind.config.ts`.
`platform/frontend/lib/__tests__/design-tokens.test.ts` recomputes and checks
everything on this page.

## Colour

Light is the default and is unchanged. Dark is the brand blue (`#3683F8`) mixed
with black, with a little white added for each step up, so the dark theme is the
same colour as the light one in less light. No surface is a neutral grey.

| Token | Light | Dark | Use |
|---|---|---|---|
| `surface` | `#EBF3FE` | `#121b2c` | Page background |
| `card` | `#FFFFFF` | `#202939` | Cards, panels, fields |
| `line` | `#D8D8D8` | `#333b4a` | Borders and dividers |
| `ink` | `#060606` | `#f2f4fa` | Body text |
| `muted` | `#8A94A6` | `#96a0b9` | Secondary text |
| `primary-soft` | `#EAF2FE` | `#182e51` | Tinted fills |
| `primary-ink` | `#2563C9` | `#78a5fa` | Links and text in the brand colour |
| `primary-fill` | `#3073DA` | `#3073DA` | Button fill |
| `primary` | `#3683F8` | `#3683F8` | Brand: icons, rings, large shapes |

The dark recipe, in order:

- `surface` = brand 14% + black 86%, then 4% white
- `card` = `surface` + 6% white
- `line` = `surface` + 14% white
- `primary-soft` = brand 18% over `surface`

Tailwind needs plain `r g b` triples for its opacity modifiers, and `color-mix`
cannot give one, so the CSS holds the result of the recipe and the test recomputes
it. To move the whole dark theme, change the 86 in the test and in `globals.css`
together and regenerate the four values.

### Which `primary` to use

- A button fill: `bg-primary-fill` (white text on it is 4.6:1). `.btn-primary`
  already does.
- Text or a link on a surface, in either theme: `text-primary-ink`.
- Anything that is not small text (an icon, a ring, a large shape): `primary`.

`text-primary` on small text is 3.7:1 on white and 4.0:1 on a dark card, below AA.
Existing uses are migrated screen by screen in the redesign, not here.

### Contrast

Every text/background pair below is at least 4.5:1 (WCAG AA) and is checked by
the test.

| Pair | Dark | Light |
|---|---|---|
| `ink` on `surface` | 15.7:1 | 18.1:1 |
| `ink` on `card` | 13.3:1 | 20.3:1 |
| `muted` on `surface` | 6.6:1 | below AA |
| `muted` on `card` | 5.6:1 | below AA |
| `primary-ink` on `surface` | 7.0:1 | 5.1:1 |
| `primary-ink` on `card` | 6.0:1 | 5.7:1 |
| `primary-ink` on `primary-soft` | 5.5:1 | 5.0:1 |

**Known gap:** the light `muted` grey is 3.1:1 on white and 2.7:1 on `surface`.
It is recorded in the test rather than hidden. The light theme does not move in
this change, so fixing it is a separate step.

## Motion

| Token | Value | Use |
|---|---|---|
| `duration-fast` | 100 ms | Press feedback |
| `duration-normal` | 200 ms | Hover, colour, focus |
| `duration-slow` | 300 ms | Cards lifting, panels |
| `ease-standard` | `cubic-bezier(.22, 1, .36, 1)` | Default for movement |
| `ease-emphasized` | `cubic-bezier(.16, 1, .3, 1)` | Larger entrances |
| `ease-sheet` | `cubic-bezier(.32, .72, 0, 1)` | Drawers and sheets |
| `ease-ios` | `cubic-bezier(.34, 1.56, .64, 1)` | The springy overshoot buttons already use |

Use them by name (`duration-normal ease-standard`), not as loose numbers.
The shared `.btn`, `.input`, `.card-interactive` and `.link-underline` styles
already do, with the same timings they had.

With `prefers-reduced-motion: reduce`, animations and transitions finish at once.
Spinners and the typing dots are the exception: they show that work is
happening.
