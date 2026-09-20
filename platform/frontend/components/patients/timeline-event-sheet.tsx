"use client";

/** Detail drawer for one Intelligent Timeline entry.
 *
 * Shows exactly what `TimelineEvent` already carries — date, type, title,
 * detail, and the AI marker — nothing fetched, nothing new on the backend. */

import { CalendarDays, FlaskConical, Image as ImageIcon, Pill, Stethoscope, type LucideIcon } from "lucide-react";
import { type TimelineEvent } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";
import Sheet from "@/components/ui/sheet";
import { useLanguage } from "@/lib/language";

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
  const { t } = useLanguage();

  const Icon = event ? iconForEventType(event.type) : CalendarDays;
  const typeKey = event ? `patientDetail.timeline.type.${event.type}` : "";
  const typeLabel = event ? (t(typeKey) === typeKey ? event.type : t(typeKey)) : "";

  return (
    <Sheet open={event !== null} onClose={onClose} side="right" title={t("patientDetail.timeline.detailTitle")}>
      {event === null ? null : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-soft">
              <Icon size={14} className="text-primary" />
            </span>
            <span className="text-sm font-semibold">{typeLabel}</span>
            {event.ai_generated && <AgentBadge name={t("patientDetail.timeline.aiExtracted")} />}
          </div>
          <div className="text-xs text-muted">{event.date}</div>
          <div className="font-semibold">{event.title}</div>
          {event.detail ? (
            <p className="whitespace-pre-wrap text-sm">{event.detail}</p>
          ) : (
            <p className="text-sm text-muted">{t("patientDetail.timeline.noDetail")}</p>
          )}
        </div>
      )}
    </Sheet>
  );
}
