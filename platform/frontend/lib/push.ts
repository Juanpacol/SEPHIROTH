/** Subscribing this browser to push.
 *
 * Every function here is called from a user gesture. `Notification.requestPermission`
 * from a page load is the pattern browsers added heuristics to punish, and it
 * deserves to be: a permission prompt nobody asked for is answered "block", and
 * a blocked permission cannot be asked for again by the page.
 */

import { api } from "@/lib/api";

export type PushPermission = "unsupported" | "default" | "granted" | "denied";

/** What this browser can do, before anything is asked of the user. */
export function pushSupport(): PushPermission {
  if (typeof window === "undefined") return "unsupported";
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "unsupported";
  if (!("Notification" in window)) return "unsupported";
  return Notification.permission as PushPermission;
}

/** The VAPID public key arrives as unpadded URL-safe base64; `PushManager`
 *  wants the raw bytes. */
function decodeKey(base64: string): ArrayBuffer {
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  // The buffer rather than the view: `applicationServerKey` accepts a
  // `BufferSource`, and TypeScript's `Uint8Array<ArrayBufferLike>` is not
  // assignable to the `ArrayBufferView<ArrayBuffer>` half of that union.
  return bytes.buffer;
}

export interface EnableResult {
  ok: boolean;
  permission: PushPermission;
  reason?: string;
}

/** Register the worker, ask for permission, subscribe, and tell the server.
 *
 * Ordered so the expensive and irreversible step — the permission prompt —
 * happens only after the cheap checks have passed. Asking someone to allow
 * notifications and then failing because the deployment has no VAPID keys
 * spends a prompt that cannot be spent twice.
 */
export async function enablePush(): Promise<EnableResult> {
  const support = pushSupport();
  if (support === "unsupported") return { ok: false, permission: support };
  if (support === "denied") {
    // The page cannot re-ask. Only the browser's own settings can undo this.
    return { ok: false, permission: "denied" };
  }

  const { enabled, public_key } = await api.pushKey();
  if (!enabled || !public_key) {
    return { ok: false, permission: support, reason: "not_configured" };
  }

  const permission = (await Notification.requestPermission()) as PushPermission;
  if (permission !== "granted") return { ok: false, permission };

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    // Required by every browser: a push that cannot be shown must not be
    // silently received.
    userVisibleOnly: true,
    applicationServerKey: decodeKey(public_key),
  });

  const json = subscription.toJSON();
  await api.subscribeToPush({
    endpoint: subscription.endpoint,
    p256dh: json.keys?.p256dh ?? "",
    auth: json.keys?.auth ?? "",
  });

  return { ok: true, permission: "granted" };
}

/** Unsubscribe this browser, server first.
 *
 * If the browser-side unsubscribe fails we have still stopped sending, which
 * is the half the user actually asked for.
 */
export async function disablePush(): Promise<void> {
  if (pushSupport() === "unsupported") return;

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;

  await api.unsubscribeFromPush(subscription.endpoint);
  await subscription.unsubscribe();
}

/** Follow a notification tap without throwing away the open tab.
 *
 * The worker focuses an existing window and posts the route to it; this is the
 * page side of that. A fresh window would discard the React tree, the query
 * cache, and any half-typed clinical note in it.
 */
export function listenForNotificationRoutes(navigate: (url: string) => void): () => void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return () => {};

  const handler = (event: MessageEvent) => {
    if (event.data?.type === "navigate" && typeof event.data.url === "string") {
      navigate(event.data.url);
    }
  };
  navigator.serviceWorker.addEventListener("message", handler);
  return () => navigator.serviceWorker.removeEventListener("message", handler);
}
