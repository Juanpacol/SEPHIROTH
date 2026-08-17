"use client";

/** Wires the previously-dead bell icon in `topbar.tsx` to the in-app
 * notification feed — no email/SMS/push channel exists, so this is the
 * whole delivery mechanism. Polls the unread count on an interval rather
 * than a websocket (no such infrastructure exists in this deployment —
 * see `Notification`'s docstring in `data/schemas`). */

import { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { api, type AppNotification } from "@/lib/api";

const POLL_INTERVAL_MS = 30_000;

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);

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

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={toggle}
        className="relative rounded-full p-2 text-muted hover:bg-primary-soft"
        aria-label="Notifications"
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
          <div className="border-b border-line/60 px-4 py-3 text-sm font-semibold">Notifications</div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 && (
              <div className="px-4 py-6 text-center text-sm text-muted">No notifications yet.</div>
            )}
            {notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => !n.read_at && markRead(n.id)}
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
