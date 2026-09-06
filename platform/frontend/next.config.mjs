import withSerwistInit from "@serwist/next";

/** Serwist generates the service worker's precache manifest at build time.
 *
 * A hand-maintained list of `/_next/static/*` URLs with build hashes in them
 * is exactly the thing that breaks silently on every deploy, which is why the
 * manifest is generated and only the `push`/`notificationclick` handlers are
 * written by hand.
 *
 * Disabled in development on purpose: a worker caching the dev server's output
 * is the most confusing thing that can happen to someone editing a page, and
 * the handlers this worker exists for are testable without it.
 */
const withSerwist = withSerwistInit({
  swSrc: "app/sw.ts",
  swDest: "public/sw.js",
  disable: process.env.NODE_ENV === "development",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Proxy API calls to the FastAPI backend (avoids CORS in dev).
    const api = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default withSerwist(nextConfig);
