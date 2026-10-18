"use client";

import { useId, useState } from "react";
import AgentBadge from "@/components/agent-badge";
import { iconForEventType } from "@/components/patients/timeline-event-sheet";
import { type TimelineEvent } from "@/lib/api";
import { useLanguage } from "@/lib/language";

/** Most recent events shown before the older ones fold behind the toggle. */
export const TIMELINE_COLLAPSED_COUNT = 5;

export default function TimelineList({
  events,
  onSelect,
}: {
  events: TimelineEvent[];
  onSelect: (event: TimelineEvent) => void;
}) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);
  const listId = useId();

  // The API returns events oldest-first, so the recent ones are the tail.
  const hiddenCount = Math.max(0, events.length - TIMELINE_COLLAPSED_COUNT);
  const firstShown = expanded ? 0 : hiddenCount;
  const shown = events.slice(firstShown);

  const toggleLabel = expanded
    ? t("patientDetail.timeline.showLess")
    : t(hiddenCount === 1 ? "patientDetail.timeline.showEarlierOne" : "patientDetail.timeline.showEarlier").replace(
        "{count}",
        String(hiddenCount),
      );

  return (
    <>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          aria-controls={listId}
          className="btn-secondary tap mb-4 py-1.5 text-xs"
        >
          {toggleLabel}
        </button>
      )}
      <ol id={listId} className="relative ml-3 space-y-5 border-l-2 border-line/60 pl-6">
        {shown.map((event, i) => {
          const Icon = iconForEventType(event.type);
          return (
            // Index in the full list, so a row keeps its key when the list expands.
            <li key={firstShown + i} className="relative">
              <span className="absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full bg-primary-soft">
                <Icon size={11} className="text-primary" />
              </span>
              <button
                type="button"
                onClick={() => onSelect(event)}
                className="tap w-full rounded-lg text-left transition-colors hover:bg-surface"
              >
                <div className="text-xs text-muted">{event.date}</div>
                <div className="flex items-center gap-2 font-semibold">
                  {event.title}
                  {event.ai_generated && <AgentBadge name={t("patientDetail.timeline.aiExtracted")} />}
                </div>
                {event.detail && <div className="text-sm text-muted">{event.detail}</div>}
              </button>
            </li>
          );
        })}
      </ol>
    </>
  );
}
