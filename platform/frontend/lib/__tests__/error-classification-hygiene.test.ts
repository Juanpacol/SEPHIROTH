/** Guards against classifying an API error by matching digits inside
 * `ApiError.message`, which is response *body* text, not the HTTP status.
 *
 * That anti-pattern only "works" by accident when the body happens to
 * contain the status code as a substring (or, historically, when a helper
 * prefixed its thrown message with the status). See
 * `.solve-task/20260920-error-classification-fix/02-spec.md` for the story
 * this guards against regressing.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../..");
const SCAN_DIRS = ["app", "components"];

// Matches `.includes("401")`, `.includes('422')`, `.includes(`413`)` — any
// 3-digit string literal passed to `.includes(...)`. Deliberately does NOT
// match `throw new Error(`${res.status}`)` (a template literal with no
// literal digits) or `err.status === 404` (not an `.includes` call).
const FORBIDDEN_PATTERN = /\.includes\(\s*["'`]\d{3}["'`]\s*\)/;

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

describe("error classification hygiene", () => {
  const files = SCAN_DIRS.flatMap((d) => sourceFiles(path.join(ROOT, d)));

  it("scans a non-trivial number of files", () => {
    // A silent glob failure would make the assertion below vacuously pass.
    expect(files.length).toBeGreaterThan(50);
  });

  it("never classifies an error by matching digits in a message string", () => {
    const hits = files
      .filter((f) => FORBIDDEN_PATTERN.test(readFileSync(f, "utf8")))
      .map((f) => path.relative(ROOT, f));

    expect(
      hits,
      `Found ${hits.length} file(s) classifying an error by matching digits in a message string: ` +
        `${hits.join(", ")}. Classify with \`err instanceof ApiError && err.status === N\` ` +
        "(see `app/portal/claim/page.tsx`), never by matching digits in `ApiError.message`, " +
        "which is the response body."
    ).toEqual([]);
  });
});
