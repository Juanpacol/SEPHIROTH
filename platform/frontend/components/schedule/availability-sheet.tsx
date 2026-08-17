"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Sheet from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type AvailabilityRule } from "@/lib/api";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function AvailabilitySheet({
  open,
  onClose,
  rules,
}: {
  open: boolean;
  onClose: () => void;
  rules: AvailabilityRule[];
}) {
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
      showToast("Working hours added.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not add working hours.", "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (ruleId: string) => {
    try {
      await api.deleteAvailabilityRule(ruleId);
      await queryClient.invalidateQueries({ queryKey: ["schedule", "availability"] });
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not remove this window.", "error");
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Working hours">
      <div className="space-y-5">
        <div className="text-xs text-muted">
          Timezone: <span className="font-semibold text-ink">{timezone}</span>
        </div>

        <div className="space-y-3">
          {rules.length === 0 && (
            <p className="text-sm text-muted">No working hours set yet.</p>
          )}
          {rules.map((r) => (
            <div key={r.id} className="card flex items-center justify-between py-3">
              <div>
                <div className="text-sm font-semibold">{WEEKDAYS[r.weekday]}</div>
                <div className="text-xs text-muted">
                  {r.start_time}–{r.end_time} · {r.slot_minutes}min slots
                </div>
              </div>
              <button
                onClick={() => remove(r.id)}
                className="text-xs font-semibold text-danger hover:underline"
              >
                Remove
              </button>
            </div>
          ))}
        </div>

        <div className="card space-y-3 py-4">
          <div className="text-sm font-semibold">Add a window</div>
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
                {m} minute slots
              </option>
            ))}
          </select>
          <button onClick={add} disabled={busy} className="btn-primary w-full">
            {busy ? "Adding…" : "Add window"}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
