"use client";

/** Turning notifications on for this device.
 *
 * Four states, and each needs different words. Not supported (nothing to
 * offer). Not configured on this deployment (nothing to offer, but for a
 * different reason, and an operator should be able to tell them apart).
 * Denied — the page cannot re-ask, so it explains where the browser setting
 * is rather than offering a button that will do nothing. And available.
 *
 * The prompt fires from the click and nowhere else. Asking on page load is the
 * pattern browsers added heuristics to punish, and it deserves to be: an
 * unsolicited prompt is answered "block", and a blocked permission cannot be
 * asked for again by the page.
 */

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, BellRing, Smartphone } from "lucide-react";

import { api } from "@/lib/api";
import { disablePush, enablePush, pushSupport, type PushPermission } from "@/lib/push";
import { useLanguage } from "@/lib/language";

const DEVICES_KEY = ["push", "devices"] as const;

export default function PushToggle() {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const [permission, setPermission] = useState<PushPermission>("unsupported");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Read after mount: `Notification.permission` does not exist on the server,
  // and reading it during render would make the first paint disagree with the
  // second.
  useEffect(() => setPermission(pushSupport()), []);

  const keyQuery = useQuery({ queryKey: ["push", "key"], queryFn: api.pushKey });
  const devices = useQuery({
    queryKey: DEVICES_KEY,
    queryFn: api.pushDevices,
    enabled: keyQuery.data?.enabled === true,
  });

  const configured = keyQuery.data?.enabled === true;
  const items = devices.data?.items ?? [];

  async function turnOn() {
    setBusy(true);
    setNotice(null);
    try {
      const result = await enablePush();
      setPermission(result.permission);
      if (!result.ok && result.permission === "denied") {
        setNotice(t("push.denied"));
      } else if (!result.ok) {
        setNotice(t("push.failed"));
      }
      await queryClient.invalidateQueries({ queryKey: DEVICES_KEY });
    } catch {
      setNotice(t("push.failed"));
    } finally {
      setBusy(false);
    }
  }

  async function turnOff() {
    setBusy(true);
    try {
      await disablePush();
      await queryClient.invalidateQueries({ queryKey: DEVICES_KEY });
    } finally {
      setBusy(false);
    }
  }

  if (permission === "unsupported") {
    return (
      <section className="card">
        <h2 className="text-sm font-semibold">{t("push.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("push.unsupported")}</p>
      </section>
    );
  }

  if (!configured) {
    // Distinct from "unsupported" on purpose: this one is an operator's
    // problem, and the two look identical if you collapse them.
    return (
      <section className="card">
        <h2 className="text-sm font-semibold">{t("push.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("push.notConfigured")}</p>
      </section>
    );
  }

  return (
    <section className="card flex flex-col gap-3">
      <header>
        <h2 className="text-sm font-semibold">{t("push.title")}</h2>
        <p className="text-sm text-muted">{t("push.help")}</p>
      </header>

      {permission === "denied" ? (
        <p className="rounded-lg bg-warning/10 px-3 py-2 text-sm">{t("push.denied")}</p>
      ) : (
        <button
          type="button"
          onClick={permission === "granted" ? turnOff : turnOn}
          disabled={busy}
          className={`tap self-start ${permission === "granted" ? "btn-secondary" : "btn-primary"} disabled:opacity-50`}
        >
          {permission === "granted" ? (
            <>
              <BellOff className="mr-1.5 inline h-4 w-4" aria-hidden />
              {t("push.disable")}
            </>
          ) : (
            <>
              <BellRing className="mr-1.5 inline h-4 w-4" aria-hidden />
              {t("push.enable")}
            </>
          )}
        </button>
      )}

      {notice ? <p className="text-sm text-danger">{notice}</p> : null}

      {items.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-ink/60">{t("push.devices")}</p>
          <ul className="mt-1 flex flex-col gap-1">
            {items.map((device) => (
              <li key={device.id} className="flex items-center gap-2 text-sm">
                <Smartphone className="h-3.5 w-3.5 text-ink/40" aria-hidden />
                <span className="min-w-0 truncate">{device.user_agent || t("push.unknownDevice")}</span>
                {device.enabled ? null : (
                  // Kept in the list rather than hidden, so "why did my old
                  // phone stop working" has an answer.
                  <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-ink/60">
                    {t("push.deviceInactive")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs text-ink/50">{t("push.noPhi")}</p>
    </section>
  );
}
