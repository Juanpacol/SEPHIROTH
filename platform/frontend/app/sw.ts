/// <reference lib="webworker" />

/** The service worker.
 *
 * Serwist generates the precache manifest — a hand-maintained list of
 * `/_next/static/*` URLs with build hashes in them is exactly the thing that
 * breaks silently on every deploy. The `push` and `notificationclick`
 * handlers are written by hand, because they are the part that carries the
 * guarantees.
 *
 * Two of those guarantees are visible here. Nothing under `/api/` is ever
 * cached (`RUNTIME_CACHE_RULES`), and the worker authenticates nothing: the
 * payload carries a route and copy with no patient content in it, and if the
 * session has expired the destination page's `AuthGuard` bounces to `/login`.
 */

import {
  CacheFirst,
  ExpirationPlugin,
  NetworkOnly,
  Serwist,
  StaleWhileRevalidate,
  type PrecacheEntry,
  type RuntimeCaching,
  type SerwistGlobalConfig,
} from "serwist";

import { RUNTIME_CACHE_RULES } from "@/lib/service-worker-policy";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

function toRuntimeCaching(rule: (typeof RUNTIME_CACHE_RULES)[number]): RuntimeCaching {
  const matcher = ({ url }: { url: URL }) => url.pathname.startsWith(rule.prefix);
  if (rule.strategy === "NetworkOnly") {
    return { matcher, handler: new NetworkOnly() };
  }
  const plugins = [new ExpirationPlugin({ maxEntries: 64, maxAgeSeconds: 86_400 })];
  return {
    matcher,
    handler:
      rule.strategy === "CacheFirst"
        ? new CacheFirst({ cacheName: "static", plugins })
        : new StaleWhileRevalidate({ cacheName: "images", plugins }),
  };
}

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  // Built from our own declared policy rather than Serwist's `defaultCache`,
  // which caches same-origin `GET /api/*` for 24 hours. See
  // `lib/service-worker-policy.ts` for why that is a leak here.
  runtimeCaching: RUNTIME_CACHE_RULES.map(toRuntimeCaching),
});

serwist.addEventListeners();

interface PushPayload {
  title: string;
  body: string;
  url: string;
  tag: string;
  notification_id: string;
}

self.addEventListener("push", (event: PushEvent) => {
  if (!event.data) return;

  let payload: PushPayload;
  try {
    payload = event.data.json() as PushPayload;
  } catch {
    // A payload we cannot read is not worth guessing at. Showing "you have a
    // notification" over unknown bytes would be inventing content.
    return;
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      // The type, never the patient: a matching tag *replaces* a notification,
      // so grouping by patient would silently drop a second critical alert.
      tag: payload.tag,
      icon: "/icon.svg",
      badge: "/icon.svg",
      data: { url: payload.url, notificationId: payload.notification_id },
    }),
  );
});

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  event.notification.close();
  const url = (event.notification.data?.url as string) ?? "/work";

  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      // Focus an open tab and tell it where to go, rather than opening a new
      // one: a fresh window throws away the React tree, the query cache and
      // any half-typed clinical note in it.
      for (const client of clients) {
        if ("focus" in client) {
          await client.focus();
          client.postMessage({ type: "navigate", url });
          return;
        }
      }
      await self.clients.openWindow(url);
    })(),
  );
});

export {};
