/** What the service worker is allowed to cache.
 *
 * A declared list rather than Serwist's `defaultCache`, and that is the whole
 * point of this file.
 *
 * `defaultCache` **caches same-origin `GET /api/*` for 24 hours** in a cache
 * named "apis" — verified by reading the generated worker while building this
 * phase, not assumed. For most Next applications that is a sensible default.
 * For this one it is a clinical-safety bug and a cross-account leak: `/api/*`
 * is a rewrite onto FastAPI, so those responses are patient records, and they
 * are bound to an `Authorization` header — a cached one on a shared clinic
 * machine is one clinician's chart served to whoever signs in next.
 *
 * Filtering a third party's list would leave the guarantee dependent on their
 * next release. Declaring ours means there is no `/api` rule to remove.
 *
 * Offline is the shell and the static assets. No background sync, no write
 * queue: a clinical write that lands hours later against a chart that has
 * moved is a class of bug worth refusing outright (SPEC-025 NG-2).
 */

export interface RuntimeCacheRule {
  /** Path prefix this rule applies to. */
  prefix: string;
  /** `NetworkOnly` means: never stored, never served from store. */
  strategy: "NetworkOnly" | "StaleWhileRevalidate" | "CacheFirst";
  why: string;
}

export const RUNTIME_CACHE_RULES: RuntimeCacheRule[] = [
  {
    prefix: "/api/",
    strategy: "NetworkOnly",
    why: "Clinical data is never served stale, and responses are bound to an Authorization header.",
  },
  {
    prefix: "/_next/static/",
    strategy: "CacheFirst",
    why: "Content-hashed build output — a given URL's bytes never change.",
  },
  {
    prefix: "/_next/image",
    strategy: "StaleWhileRevalidate",
    why: "Optimised images. Carries no clinical content and is expensive to refetch.",
  },
];

/** Whether a path may be stored at all. */
export function mayCache(pathname: string): boolean {
  const rule = ruleFor(pathname);
  return rule ? rule.strategy !== "NetworkOnly" : false;
}

/** The rule that governs a path, or undefined when none does.
 *
 * A path with no rule is not cached: the worker falls through to the network,
 * which is the safe default for anything nobody has reasoned about.
 */
export function ruleFor(pathname: string): RuntimeCacheRule | undefined {
  return RUNTIME_CACHE_RULES.find((candidate) => pathname.startsWith(candidate.prefix));
}
