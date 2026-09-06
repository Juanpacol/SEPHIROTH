/** Lint-by-test for the two mistakes that make a page unusable on a phone.
 *
 * There is no e2e harness here, and a visual-diff baseline across four widths
 * and a dozen pages is a maintenance liability nobody has budget for. These two
 * rules are not a substitute for looking at the app — they are the cheap part
 * that catches a regression on the way in, so the manual pass at 375/768/1024/
 * 1440 stays a check rather than a hunt.
 *
 * Both rules carry an explicit exception list. The point is not to forbid the
 * pattern; it is to make using it a decision someone wrote down.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry === "__tests__") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.tsx?$/.test(full)) out.push(full);
  }
  return out;
}

const FILES = [...sourceFiles(join(ROOT, "app")), ...sourceFiles(join(ROOT, "components"))].map((f) => ({
  path: relative(ROOT, f),
  text: readFileSync(f, "utf8"),
}));

describe("responsive guardrails", () => {
  /** A raw table has no card shape, so it either overflows a 375px screen or
   * gets a horizontal scrollbar nobody discovers. `DataList` renders both
   * shapes from one column definition. */
  it("AC-017-12 — routes every table through DataList", () => {
    const ALLOWED = new Set(["components/ui/data-list.tsx"]);

    const offenders = FILES.filter(
      (f) => !ALLOWED.has(f.path) && /<table[\s>]/.test(f.text),
    ).map((f) => f.path);

    expect(offenders, "use <DataList> instead of a raw <table>, or add a reasoned exception").toEqual(
      [],
    );
  });

  /** A fixed pixel width wider than the narrowest supported viewport (375px)
   * forces the whole page to scroll sideways unless it sits inside its own
   * scroll container. Each exception below names why. */
  it("AC-017-13 — keeps fixed widths under the narrowest viewport", () => {
    const ALLOWED: Record<string, string> = {
      // The weekly grid is genuinely wide and lives in its own overflow-x
      // container; the phone gets a day view in the agenda rework.
      "app/schedule/page.tsx": "week grid, inside its own horizontal scroller",
    };

    const offenders = FILES.flatMap((f) => {
      if (ALLOWED[f.path]) return [];
      const matches = f.text.match(/(?:min-)?w-\[(\d+)px\]/g) ?? [];
      const tooWide = matches.filter((m) => Number(m.match(/(\d+)px/)![1]) > 375);
      return tooWide.length > 0 ? [`${f.path}: ${tooWide.join(", ")}`] : [];
    });

    expect(offenders, "a fixed width above 375px scrolls the page sideways on a phone").toEqual([]);
  });

  /** The bottom navigation is fixed and 64px tall; a page whose content ends
   * flush with the viewport hides its last row underneath it. */
  it("AC-017-14 — keeps the app shell clear of the fixed bottom bar", () => {
    const shell = FILES.find((f) => f.path === "components/app-shell.tsx")!;
    expect(shell.text).toMatch(/pb-24/);
  });
});
