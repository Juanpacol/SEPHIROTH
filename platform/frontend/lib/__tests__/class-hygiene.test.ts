/** Guards against Tailwind classes that look plausible but are not defined —
 * they compile fine, ship fine, and silently render nothing.
 *
 * This exists because `border-border` reached production in 17 places: the
 * project's border token is `line` (see `tailwind.config.ts`), `border` is not
 * a color at all, and every one of those borders was invisible. Nothing caught
 * it — a typo'd utility is not a type error and not a lint error.
 *
 * Add to `FORBIDDEN` whenever a class turns out to be a ghost. Cheap insurance
 * against the same string coming back by copy-paste.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../..");
const SCAN_DIRS = ["app", "components"];

const FORBIDDEN: { className: string; instead: string }[] = [
  { className: "border-border", instead: "border-line (the color token is `line`, not `border`)" },
];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

describe("Tailwind class hygiene", () => {
  const files = SCAN_DIRS.flatMap((d) => sourceFiles(path.join(ROOT, d)));

  it("scans a non-trivial number of files", () => {
    // A silent glob failure would make every assertion below vacuously pass.
    expect(files.length).toBeGreaterThan(50);
  });

  it.each(FORBIDDEN)("never uses `$className`", ({ className, instead }) => {
    // Word boundaries so `border-border` doesn't match a longer real class.
    const pattern = new RegExp(`(?<![\\w-])${className}(?![\\w-])`);
    const hits = files
      .filter((f) => pattern.test(readFileSync(f, "utf8")))
      .map((f) => path.relative(ROOT, f));

    expect(hits, `\`${className}\` is not a defined class — use ${instead}`).toEqual([]);
  });
});
