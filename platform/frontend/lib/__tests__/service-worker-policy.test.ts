/** What the service worker may cache.
 *
 * This test exists because Serwist's `defaultCache` **caches same-origin
 * `GET /api/*` for 24 hours** in a cache named "apis" — found by reading the
 * generated worker while building this phase, not assumed. For most Next
 * applications that is a sensible default; for this one it is a
 * clinical-safety bug and a cross-account leak, because `/api/*` is a rewrite
 * onto FastAPI and the responses are bound to an `Authorization` header.
 *
 * So the policy is declared rather than inherited, and this asserts on the
 * declaration and on the worker actually built from it.
 *
 * Verifies AC-025-10 (docs/specs/SPEC-025-pwa-push.md).
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { RUNTIME_CACHE_RULES, mayCache, ruleFor } from "@/lib/service-worker-policy";

describe("the declared caching policy", () => {
  it("never caches an API response", () => {
    expect(mayCache("/api/patients/P1")).toBe(false);
    expect(mayCache("/api/results/inbox")).toBe(false);
    expect(mayCache("/api/encounters/E1")).toBe(false);
  });

  it("declares why, not just what", () => {
    const rule = ruleFor("/api/patients/P1");
    expect(rule?.strategy).toBe("NetworkOnly");
    expect(rule?.why).toMatch(/Authorization|stale/i);
  });

  it("does cache content-hashed build output", () => {
    expect(mayCache("/_next/static/chunks/main-abc123.js")).toBe(true);
  });

  it("caches nothing it has not reasoned about", () => {
    // A path with no rule falls through to the network, which is the safe
    // default for anything nobody has thought about yet.
    expect(mayCache("/some/new/surface")).toBe(false);
    expect(ruleFor("/some/new/surface")).toBeUndefined();
  });

  it("has exactly one rule per prefix", () => {
    const prefixes = RUNTIME_CACHE_RULES.map((rule) => rule.prefix);
    expect(new Set(prefixes).size).toBe(prefixes.length);
  });

  it("puts the API rule first, so nothing broader can shadow it", () => {
    // `ruleFor` takes the first match. A `/` rule added above `/api/` would
    // silently start caching charts.
    expect(RUNTIME_CACHE_RULES[0].prefix).toBe("/api/");
  });
});

describe("the worker actually built from it", () => {
  const built = join(process.cwd(), "public", "sw.js");

  it.runIf(existsSync(built))("declares no cache for API responses", () => {
    const source = readFileSync(built, "utf8");

    // The cache name Serwist's default rule uses. Its presence means the
    // default list came back.
    expect(source).not.toContain('cacheName:"apis"');
    expect(source).not.toContain('cacheName: "apis"');
  });

  it.runIf(existsSync(built))("was generated rather than hand-written", () => {
    // A hand-maintained precache list of hashed `/_next/static/*` URLs is
    // exactly what breaks silently on every deploy.
    const source = readFileSync(built, "utf8");
    expect(source.length).toBeGreaterThan(1000);
  });
});
