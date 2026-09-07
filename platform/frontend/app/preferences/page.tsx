"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";

// This clinic is single-tenant (CLAUDE.md decision #7 -- no per-clinician
// scoping); automation_memory.py's own docstring confirms `scope="clinic"`
// accepts any scope_id since there's no backing table for it. A fixed id
// is the simplest thing that works until multi-tenant is a real need.
const CLINIC_SCOPE_ID = "default";

function useMemoryField(key: string, defaultValue: string) {
  const { t } = useLanguage();
  const [value, setValue] = useState(defaultValue);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .readAutomationMemory("clinic", CLINIC_SCOPE_ID, key)
      .then((res) => {
        if (res.value !== null && res.value !== undefined) setValue(String(res.value));
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const save = async (parsed: unknown) => {
    setError("");
    setSaved(false);
    setBusy(true);
    try {
      await api.writeAutomationMemory("clinic", CLINIC_SCOPE_ID, key, parsed);
      setSaved(true);
    } catch {
      setError(t("preferences.error.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return { value, setValue, busy, error, saved, save };
}

export default function PreferencesPage() {
  const { t } = useLanguage();
  const leadHours = useMemoryField("reminder_lead_hours", "24");
  const [quietStartValue, setQuietStartValue] = useState("22:00");
  const [quietEndValue, setQuietEndValue] = useState("07:00");
  const [quietBusy, setQuietBusy] = useState(false);
  const [quietError, setQuietError] = useState("");
  const [quietSaved, setQuietSaved] = useState(false);

  useEffect(() => {
    api
      .readAutomationMemory("clinic", CLINIC_SCOPE_ID, "quiet_hours")
      .then((res) => {
        const v = res.value as { start?: string; end?: string } | null;
        if (v?.start) setQuietStartValue(v.start);
        if (v?.end) setQuietEndValue(v.end);
      })
      .catch(() => {});
  }, []);

  const saveLeadHours = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = Number(leadHours.value);
    if (!Number.isInteger(n) || n < 1 || n > 168) return;
    await leadHours.save(n);
  };

  const saveQuietHours = async (e: React.FormEvent) => {
    e.preventDefault();
    setQuietError("");
    setQuietSaved(false);
    setQuietBusy(true);
    try {
      await api.writeAutomationMemory("clinic", CLINIC_SCOPE_ID, "quiet_hours", {
        start: quietStartValue,
        end: quietEndValue,
      });
      setQuietSaved(true);
    } catch {
      setQuietError(t("preferences.quietHours.error.saveFailed"));
    } finally {
      setQuietBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-xl font-extrabold">{t("preferences.title")}</h1>
        <p className="text-sm text-muted">{t("preferences.subtitle")}</p>
      </div>

      <form onSubmit={saveLeadHours} className="card space-y-4">
        <h2 className="font-bold">{t("preferences.leadTime.title")}</h2>
        <div>
          <label className="mb-1 block text-sm font-semibold">{t("preferences.leadTime.label")}</label>
          <input
            type="number"
            min={1}
            max={168}
            value={leadHours.value}
            onChange={(e) => leadHours.setValue(e.target.value)}
            className="input"
          />
        </div>
        {leadHours.error && <p className="text-sm text-danger">{leadHours.error}</p>}
        {leadHours.saved && <p className="text-sm text-success">{t("preferences.saved")}</p>}
        <button type="submit" disabled={leadHours.busy} className="btn-primary">
          {leadHours.busy ? t("preferences.saving") : t("preferences.save")}
        </button>
      </form>

      <form onSubmit={saveQuietHours} className="card space-y-4">
        <h2 className="font-bold">{t("preferences.quietHours.title")}</h2>
        <p className="text-sm text-muted">{t("preferences.quietHours.subtitle")}</p>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-semibold">{t("preferences.quietHours.start")}</label>
            <input
              type="time"
              value={quietStartValue}
              onChange={(e) => setQuietStartValue(e.target.value)}
              className="input"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-sm font-semibold">{t("preferences.quietHours.end")}</label>
            <input
              type="time"
              value={quietEndValue}
              onChange={(e) => setQuietEndValue(e.target.value)}
              className="input"
            />
          </div>
        </div>
        {quietError && <p className="text-sm text-danger">{quietError}</p>}
        {quietSaved && <p className="text-sm text-success">{t("preferences.saved")}</p>}
        <button type="submit" disabled={quietBusy} className="btn-primary">
          {quietBusy ? t("preferences.saving") : t("preferences.save")}
        </button>
      </form>
    </div>
  );
}
