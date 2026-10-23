"use client";

/** The week's seven days as a swipeable strip — the phone's replacement for the
 * week grid's column headers. Picks which day `day-agenda.tsx` shows. */

import { useEffect, useRef } from "react";
import { format } from "date-fns";

export default function DayStrip({
  days,
  selected,
  onSelect,
  countFor,
}: {
  days: Date[];
  selected: Date;
  onSelect: (day: Date) => void;
  /** How many appointments that day holds — a dot under the number, so a week
   * can be read at a glance without opening each day. */
  countFor: (day: Date) => number;
}) {
  const selectedRef = useRef<HTMLButtonElement | null>(null);
  const selectedKey = format(selected, "yyyy-MM-dd");
  const todayKey = format(new Date(), "yyyy-MM-dd");

  // Keep the chosen day on screen when the week changes under it.
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [selectedKey]);

  return (
    <div className="-mx-4 flex snap-x snap-mandatory gap-2 overflow-x-auto px-4">
      {days.map((day) => {
        const key = format(day, "yyyy-MM-dd");
        const isSelected = key === selectedKey;
        const count = countFor(day);
        return (
          <button
            key={key}
            ref={isSelected ? selectedRef : null}
            onClick={() => onSelect(day)}
            aria-current={isSelected ? "date" : undefined}
            className={`tap w-14 shrink-0 snap-start rounded-2xl border py-2 text-center transition-colors duration-normal ${
              isSelected
                ? "border-primary-ink/60 bg-primary-soft/60 text-ink"
                : "border-line/50 text-muted hover:border-line"
            } ${!isSelected && key === todayKey ? "!border-primary-ink/40" : ""}`}
          >
            <span className={`eyebrow block ${isSelected ? "text-primary-ink" : ""}`}>
              {format(day, "EEE")}
            </span>
            <span className="block font-display text-2xl font-light leading-tight">{format(day, "d")}</span>
            <span
              className={`mx-auto mt-0.5 block h-1 w-1 rounded-full ${
                count > 0 ? "bg-primary-ink" : "bg-transparent"
              }`}
              aria-hidden="true"
            />
          </button>
        );
      })}
    </div>
  );
}
