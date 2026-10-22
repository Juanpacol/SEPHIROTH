# Fonts

`Manrope-latin-wght.woff2` is Manrope's variable font (weight axis 200-800),
`latin` subset only, loaded in `app/layout.tsx` through `next/font/local`.

- **Source:** `@fontsource-variable/manrope` 5.3.0, file `files/manrope-latin-wght-normal.woff2`.
- **License:** SIL Open Font License 1.1, copy in `OFL.txt` (the license requires it to travel with the font).
- **Why it is in the repo:** `next/font/google` fetches the font from Google while
  building, and a failed fetch fails the whole build (CI and Vercel previews).

To update it, download the same file from a newer `@fontsource-variable/manrope`
release and replace it; keep the file name so `layout.tsx` needs no change.

## Display and label fonts (AB#40)

Both are variable fonts, `latin` subset only, loaded in `app/layout.tsx` through
`next/font/local` for the same reason as Manrope. The license of each travels with it.

| File | Use | Weights | Source | License |
|---|---|---|---|---|
| `Antonio-latin-wght.woff2` | Display: the landing's large headings (`font-display`) | 100-700 | `@fontsource-variable/antonio` 5.3.0 | OFL 1.1, `OFL-Antonio.txt` |
| `JetBrainsMono-latin-wght.woff2` | Labels: the small uppercase eyebrows (`.eyebrow`, `font-mono`) | 100-800 | `@fontsource-variable/jetbrains-mono` 5.3.0 | OFL 1.1, `OFL-JetBrainsMono.txt` |

No trial or commercial font is used anywhere. The typography the redesign takes
as a reference uses licensed fonts; these are free stand-ins with the same
character (a tall condensed display face, a mono label face), not copies.

To update one, download the same file from a newer release of its package and keep
the file name.
