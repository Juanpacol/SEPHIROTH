/** Grain over the backdrop, in the landing's manner (`feature-media.tsx`'s own `Grain`): the same noise
 * texture over the whole surface, so a stretch of the photo with little in it still reads as print
 * texture instead of "the image ran out" — most visible on an ultra-wide viewport, where the square
 * source has a lot of plain backdrop around the subject. */
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E\")";

/** The full-bleed backdrop behind the login/claim card: one of the landing's duotone studies,
 * tinted to the same deep blue-violet as `.copilot-skin` with fixed colors (not theme tokens),
 * so the page reads the same whichever theme the visitor last chose — paired with `ForceDark`
 * on the page itself so the card and copy sitting on top render in the dark palette too.
 *
 * The photo is a square study; at a wide desktop viewport `object-cover` shows its full width
 * with no horizontal crop, so a slight zoom tightens the composition instead of leaving its own
 * plain backdrop stretched thin, and a vignette centred on the card reads that framing as
 * deliberate depth rather than empty space. */
export default function AuthBackdrop() {
  return (
    <div aria-hidden="true" className="absolute inset-0 overflow-hidden bg-[#0d1330]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/landing/auth/login-xray.webp"
        alt=""
        className="absolute inset-0 h-full w-full scale-110 object-cover opacity-80 [filter:grayscale(1)_contrast(1.2)]"
      />
      <div className="absolute inset-0 bg-[#1f2fa0] mix-blend-multiply" />
      <div className="absolute inset-0 bg-[#6f7bff]/25 mix-blend-screen" />
      <div
        aria-hidden="true"
        className="absolute inset-0 mix-blend-overlay opacity-30"
        style={{ backgroundImage: GRAIN }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(60%_55%_at_50%_42%,transparent_0%,rgb(13_19_48/0.55)_70%,rgb(13_19_48/0.88)_100%)]" />
      <div className="absolute inset-0 bg-gradient-to-b from-[#0d1330]/60 via-transparent to-[#0d1330]/80" />
    </div>
  );
}
