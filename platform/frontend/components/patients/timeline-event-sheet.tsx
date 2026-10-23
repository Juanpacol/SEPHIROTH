"use client";

/** Detail drawer for one Intelligent Timeline entry.
 *
 * Shows exactly what `TimelineEvent` already carries — date, type, title,
 * detail, and the AI marker — nothing fetched, nothing new on the backend. */

import {
  CalendarDays,
  FlaskConical,
  Image as ImageIcon,
  Pill,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";
import { type TimelineEvent } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";
import EventThumb from "@/components/patients/event-thumb";
import Sheet from "@/components/ui/sheet";
import { useLanguage } from "@/lib/language";
import { formatEventDate, parseEventDetail } from "@/lib/timeline-detail";

const eventIcons: Record<string, LucideIcon> = {
  diagnosis: Stethoscope,
  medication: Pill,
  lab: FlaskConical,
  imaging: ImageIcon,
  event: CalendarDays,
};

export function iconForEventType(type: string): LucideIcon {
  return eventIcons[type] ?? CalendarDays;
}

export default function TimelineEventSheet({
  event,
  onClose,
}: {
  event: TimelineEvent | null;
  onClose: () => void;
}) {
  const { t, lang } = useLanguage();

  const Icon = event ? iconForEventType(event.type) : CalendarDays;
  const parsed = event ? parseEventDetail(event.detail) : null;
  const typeKey = event ? `patientDetail.timeline.type.${event.type}` : "";
  const typeLabel = event ? (t(typeKey) === typeKey ? event.type : t(typeKey)) : "";

  return (
    <Sheet
      open={event !== null}
      onClose={onClose}
      side="right"
      title={t("patientDetail.timeline.detailTitle")}
    >
      {event === null ? null : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-soft">
              <Icon size={14} className="text-primary" />
            </span>
            <span className="text-sm font-semibold">{typeLabel}</span>
            {event.ai_generated && <AgentBadge name={t("patientDetail.timeline.aiExtracted")} />}
          </div>
          {parsed?.imagePath && (
            <EventThumb path={parsed.imagePath} alt={event.title} className="aspect-[4/3] w-full" />
          )}
          <div className="eyebrow text-muted">{formatEventDate(event.date, lang)}</div>
          <div className="font-semibold">{event.title}</div>
          {parsed?.model && (
            <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{parsed.model}</div>
          )}
          {parsed?.text ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{parsed.text}</p>
          ) : (
            <p className="text-sm text-muted">{t("patientDetail.timeline.noDetail")}</p>
          )}
        </div>
      )}
    </Sheet>
  );
}
