"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Sheet from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type AvailabilityRule } from "@/lib/api";
import { useLanguage } from "@/lib/language";

export default function AvailabilitySheet({
  open,
  onClose,
  rules,
}: {
  open: boolean;
  onClose: () => void;
  rules: AvailabilityRule[];
}) {
  const { t } = useLanguage();
  const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6].map((i) => t(`schedule.weekday.${i}`));
  const queryClient = useQueryClient();
  const showToast = useToast();
  const [weekday, setWeekday] = useState(0);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("17:00");
  const [slotMinutes, setSlotMinutes] = useState(30);
  const [busy, setBusy] = useState(false);

  const timezone =
    typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "UTC";

  const add = async () => {
    setBusy(true);
    try {
      await api.createAvailabilityRule({
        weekday,
        start_time: start,
        end_time: end,
        slot_minutes: slotMinutes,
        timezone,
      });
      await queryClient.invalidateQueries({ queryKey: ["schedule", "availability"] });
      showToast(t("schedule.availability.added"));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("schedule.availability.error.add"), "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (ruleId: string) => {
    try {
      await api.deleteAvailabilityRule(ruleId);
      await queryClient.invalidateQueries({ queryKey: ["schedule", "availability"] });
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("schedule.availability.error.remove"), "error");
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("schedule.workingHours")}>
      <div className="space-y-5">
        <div className="text-xs text-muted">
          {t("schedule.availability.timezone")} <span className="font-semibold text-ink">{timezone}</span>
        </div>

        <div className="space-y-3">
          {rules.length === 0 && (
            <p className="text-sm text-muted">{t("schedule.availability.none")}</p>
          )}
          {rules.map((r) => (
            <div key={r.id} className="card flex items-center justify-between py-3">
              <div>
                <div className="text-sm font-semibold">{WEEKDAYS[r.weekday]}</div>
                <div className="text-xs text-muted">
                  {r.start_time}–{r.end_time} ·{" "}
                  {t("schedule.availability.slotsLabel").replace("{minutes}", String(r.slot_minutes))}
                </div>
              </div>
              <button
                onClick={() => remove(r.id)}
                className="text-xs font-semibold text-danger hover:underline"
              >
                {t("schedule.availability.remove")}
              </button>
            </div>
          ))}
        </div>

        <div className="card space-y-3 py-4">
          <div className="text-sm font-semibold">{t("schedule.availability.addWindow")}</div>
          <select
            value={weekday}
            onChange={(e) => setWeekday(Number(e.target.value))}
            className="input"
          >
            {WEEKDAYS.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className="input" />
            <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className="input" />
          </div>
          <select
            value={slotMinutes}
            onChange={(e) => setSlotMinutes(Number(e.target.value))}
            className="input"
          >
            {[15, 20, 30, 45, 60].map((m) => (
              <option key={m} value={m}>
                {t("schedule.availability.slotMinutes").replace("{count}", String(m))}
              </option>
            ))}
          </select>
          <button onClick={add} disabled={busy} className="btn-primary w-full">
            {busy ? t("schedule.availability.adding") : t("schedule.availability.add")}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
