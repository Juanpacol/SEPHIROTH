"use client";

/** Wires the previously-dead bell icon in `topbar.tsx` to the in-app
 * notification feed — no email/SMS/push channel exists, so this is the
 * whole delivery mechanism. Polls the unread count on an interval rather
 * than a websocket (no such infrastructure exists in this deployment —
 * see `Notification`'s docstring in `data/schemas`). */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import { api, type AppNotification } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";

const POLL_INTERVAL_MS = 30_000;

/** Where clicking a notification navigates to, per role -- a patient and
 * a clinician land on different routes for the same event type (e.g. an
 * appointment lives at /portal/appointments for a patient, /schedule for
 * a clinician), and some types are role-exclusive in practice (only
 * clinicians receive "alert_escalated", only patients receive the rest
 * today). Undefined means "no known destination" -- falls back to just
 * marking the notification read, the previous behavior. */
function destinationFor(type: AppNotification["type"], role: string | undefined): string | undefined {
  if (role === "clinician") {
    if (type === "alert_escalated") return "/alerts";
    if (type === "appointment_booked" || type === "waitlist_match") return "/schedule";
    return undefined;
  }
  switch (type) {
    case "appointment_booked":
    case "appointment_reminder":
    case "waitlist_match":
      return "/portal/appointments";
    case "result_shared":
      return "/portal/results";
    case "medication_prescribed":
    case "followup_message":
      return "/portal";
    default:
      return undefined;
  }
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const router = useRouter();
  const user = useUser();
  const { t } = useLanguage();

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const { count } = await api.unreadNotificationCount();
        if (!cancelled) setUnread(count);
      } catch {
        // Not signed in yet, or a transient network error — the badge
        // just stays at its last known value.
      }
    };
    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next) {
      const list = await api.listNotifications();
      setNotifications(list);
    }
  };

  const markRead = async (id: string) => {
    await api.markNotificationRead(id);
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    setUnread((prev) => Math.max(0, prev - 1));
  };

  const openNotification = (n: AppNotification) => {
    if (!n.read_at) markRead(n.id);
    const destination = destinationFor(n.type, user?.role);
    if (destination) {
      setOpen(false);
      router.push(destination);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={toggle}
        className="relative rounded-full p-2 text-muted hover:bg-primary-soft"
        aria-label={t("notifications.title")}
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="glass-surface absolute right-0 top-full z-20 mt-2 w-80 rounded-squircle border border-line/60 shadow-card">
          <div className="border-b border-line/60 px-4 py-3 text-sm font-semibold">
            {t("notifications.title")}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 && (
              <div className="px-4 py-6 text-center text-sm text-muted">
                {t("notifications.empty")}
              </div>
            )}
            {notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => openNotification(n)}
                className={`block w-full border-b border-line/40 px-4 py-3 text-left text-sm last:border-b-0 hover:bg-primary-soft ${
                  n.read_at ? "text-muted" : "font-medium text-ink"
                }`}
              >
                {n.message}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
