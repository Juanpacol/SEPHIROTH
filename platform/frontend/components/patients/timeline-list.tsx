"use client";

import { useId, useState } from "react";
import AgentBadge from "@/components/agent-badge";
import EventThumb from "@/components/patients/event-thumb";
import { iconForEventType } from "@/components/patients/timeline-event-sheet";
import { type TimelineEvent } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { formatEventDate, parseEventDetail, summarize } from "@/lib/timeline-detail";

/** Most recent events shown before the older ones fold behind the toggle. */
export const TIMELINE_COLLAPSED_COUNT = 5;

/** The seeded and extracted events often carry this stock sentence as their detail; it says nothing the
 * title does not, so it is not repeated under every row. */
const GENERIC_DETAIL = /^recorded in the clinical timeline/i;

export default function TimelineList({
  events,
  onSelect,
}: {
  events: TimelineEvent[];
  onSelect: (event: TimelineEvent) => void;
}) {
  const { t, lang } = useLanguage();
  const [expanded, setExpanded] = useState(false);
  const listId = useId();

  // The API returns events oldest-first; a chart reads newest first, so the list is turned around.
  const newestFirst = [...events].reverse();
  const hiddenCount = Math.max(0, newestFirst.length - TIMELINE_COLLAPSED_COUNT);
  const shown = expanded ? newestFirst : newestFirst.slice(0, TIMELINE_COLLAPSED_COUNT);

  const toggleLabel = expanded
    ? t("patientDetail.timeline.showLess")
    : t(
        hiddenCount === 1 ? "patientDetail.timeline.showEarlierOne" : "patientDetail.timeline.showEarlier"
      ).replace("{count}", String(hiddenCount));

  return (
    <>
      <ol id={listId} className="relative ml-3 space-y-1 border-l border-line/60 pl-6">
        {shown.map((event, i) => {
          const Icon = iconForEventType(event.type);
          const parsed = parseEventDetail(event.detail);
          // A long description is read in full in the detail drawer; the row keeps its opening sentence.
          const detail = parsed.text && !GENERIC_DETAIL.test(parsed.text) ? summarize(parsed.text) : "";
          return (
            <li
              key={`${event.date}-${event.title}-${i}`}
              style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
              className="relative animate-fadeIn [animation-fill-mode:both]"
            >
              <span className="absolute -left-[33px] top-3.5 flex h-[15px] w-[15px] items-center justify-center rounded-full bg-surface ring-1 ring-line">
                <Icon size={9} strokeWidth={2} className="text-primary-ink" />
              </span>
              <button
                type="button"
                onClick={() => onSelect(event)}
                className="tap group/ev w-full rounded-xl px-3 py-2 text-left transition-colors duration-normal hover:bg-primary-soft/30"
              >
                <div className="flex items-start gap-3">
                  {parsed.imagePath && <EventThumb path={parsed.imagePath} alt={event.title} />}
                  <div className="min-w-0 flex-1">
                    <div className="eyebrow text-muted">{formatEventDate(event.date, lang)}</div>
                    <div className="mt-0.5 flex items-center gap-2 font-semibold">
                      {event.title}
                      {event.ai_generated && <AgentBadge name={t("patientDetail.timeline.aiExtracted")} />}
                    </div>
                    {detail && <div className="mt-0.5 line-clamp-2 text-sm text-muted">{detail}</div>}
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ol>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          aria-controls={listId}
          className="nav-underline tap mt-3 px-3 py-2 text-sm font-medium text-muted hover:text-ink"
        >
          {toggleLabel}
        </button>
      )}
    </>
  );
}
