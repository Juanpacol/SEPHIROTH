import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/** `.band-dark` re-themes a section of a light page by setting the dark theme's tokens
 * on itself. If it drifted from `.dark`, a navy band would be a different navy. */
const css = readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");
const vars = (selector: string) => {
  const body = css.match(new RegExp(`${selector}\\s*\\{([^}]*)\\}`))?.[1] ?? "";
  return Object.fromEntries(
    Array.from(body.matchAll(/--([\w-]+):\s*([^;]+);/g)).map((m) => [m[1], m[2].trim()]),
  );
};

describe("band-dark", () => {
  it("sets exactly the dark theme's colour and shadow tokens", () => {
    const dark = vars("\\.dark");
    const band = vars("\\.band-dark");
    expect(Object.keys(band).sort()).toEqual(Object.keys(dark).sort());
    expect(band).toEqual(dark);
  });

  it("paints its own background and text, so it works on a light page", () => {
    expect(css).toMatch(/\.band-dark\s*\{[^}]*@apply bg-surface text-ink;/);
  });
});
