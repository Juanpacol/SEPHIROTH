# Fonts

`Manrope-latin-wght.woff2` is Manrope's variable font (weight axis 200-800),
`latin` subset only, loaded in `app/layout.tsx` through `next/font/local`.

- **Source:** `@fontsource-variable/manrope` 5.3.0, file `files/manrope-latin-wght-normal.woff2`.
- **License:** SIL Open Font License 1.1, copy in `OFL.txt` (the license requires it to travel with the font).
- **Why it is in the repo:** `next/font/google` fetches the font from Google while
  building, and a failed fetch fails the whole build (CI and Vercel previews).

To update it, download the same file from a newer `@fontsource-variable/manrope`
release and replace it; keep the file name so `layout.tsx` needs no change.
