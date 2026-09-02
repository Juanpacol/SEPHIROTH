import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  FileCheck2,
  FlaskConical,
  HelpCircle,
  type LucideIcon,
  Pill,
  ScanLine,
  ShieldAlert,
  TrendingDown,
} from "lucide-react";
import { api, type DashboardActionItem } from "@/lib/api";
import { parseInteractionLabel } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import { useToast } from "@/components/ui/toast";

const CATEGORY_ICON: Record<DashboardActionItem["category"], LucideIcon> = {
  alert: ShieldAlert,
  deteriorating: TrendingDown,
  lab: FlaskConical,
  interaction: Pill,
  imaging: ScanLine,
  followup: CalendarClock,
  approval: FileCheck2,
  decision: HelpCircle,
};

export function itemText(item: DashboardActionItem, t: (key: string) => string): string {
  switch (item.category) {
    case "alert": {
      // Alert rows generated for a drug interaction carry a title like
      // "Interaction: clopidogrel + warfarin" plus a formal `detail`
      // sentence written for the /alerts audit log — right for an audit
      // trail, not for a doctor skimming a to-do list. Re-rendered with
      // the same plain phrasing as the `interaction` category below,
      // dropping the jargon sentence entirely.
      const interaction = parseInteractionLabel(item.title);
      if (interaction) {
        return t("clinical.interaction").replace("{drugA}", interaction.drugA).replace("{drugB}", interaction.drugB);
      }
      return item.detail ? `${item.title} — ${item.detail}` : item.title ?? "";
    }
    case "deteriorating":
      return t("dashboard.actionItems.deteriorating");
    case "lab":
      return t("dashboard.actionItems.lab")
        .replace("{test}", item.test_name ?? "")
        .replace("{value}", String(item.value ?? ""))
        .replace("{unit}", item.unit ?? "");
    case "interaction":
      return t("clinical.interaction")
        .replace("{drugA}", item.drug_a ?? "")
        .replace("{drugB}", item.drug_b ?? "");
    case "imaging":
      return t("dashboard.actionItems.imaging")
        .replace("{modality}", (item.modality ?? "").toUpperCase())
        .replace("{bodyPart}", item.body_part ?? "")
        .replace(
          "{status}",
          item.severity === "critical"
            ? t("dashboard.actionItems.imagingCritical")
            : t("dashboard.actionItems.imagingReview")
        );
    case "followup": {
      const check = t(`dashboard.actionItems.followupCheck.${item.check_key}`);
      return t("dashboard.actionItems.followup")
        .replace("{check}", check)
        .replace("{days}", String(item.days_late ?? 0));
    }
    case "approval":
      return t("dashboard.actionItems.approval");
    case "decision":
      return t("dashboard.actionItems.decision").replace("{query}", item.query_preview ?? "");
    default:
      return "";
  }
}

function ResolveDecisionButton({ consultationId }: { consultationId: string }) {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const showToast = useToast();

  const resolve = useMutation({
    mutationFn: () => api.markActedOn(consultationId, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard", "bootstrap"] });
      showToast(t("dashboard.actionItems.markedActedOn"));
    },
    onError: () => showToast(t("dashboard.actionItems.error.markActedOn"), "error"),
  });

  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        resolve.mutate();
      }}
      disabled={resolve.isPending}
      className="shrink-0 rounded-full bg-primary-soft px-2.5 py-1 text-xs font-semibold text-primary hover:brightness-95 disabled:opacity-40"
    >
      {resolve.isPending ? t("dashboard.actionItems.markingActedOn") : t("dashboard.actionItems.markActedOn")}
    </button>
  );
}

export default function ActionItemsList({
  items,
  maxVisible,
}: {
  items: DashboardActionItem[];
  /** Caps how many rows render — the dashboard needs the worst few at a
   * glance, not the full ranked list, to keep this off a second scroll. */
  maxVisible?: number;
}) {
  const { t } = useLanguage();

  if (items.length === 0) {
    return <p className="text-sm text-muted">{t("dashboard.actionItems.empty")}</p>;
  }
  const visible = maxVisible ? items.slice(0, maxVisible) : items;
  const hiddenCount = items.length - visible.length;

  return (
    <>
      <ul className="divide-y divide-line/60">
        {visible.map((item, i) => {
          const Icon = CATEGORY_ICON[item.category];
          const content = (
            <div className="flex min-w-0 items-center gap-2.5">
              <Icon
                size={14}
                className={`shrink-0 ${item.severity === "critical" || item.severity === "high" ? "text-danger" : "text-warning"}`}
              />
              <div className="min-w-0">
                {item.patient_name && (
                  <div className="truncate text-sm font-semibold leading-tight">{item.patient_name}</div>
                )}
                <div className="truncate text-xs leading-tight text-muted">{itemText(item, t)}</div>
              </div>
            </div>
          );
          return (
            <li
              key={`${item.category}-${item.patient_id ?? "none"}-${i}`}
              className="flex items-center gap-2 py-1.5"
            >
              {item.patient_id ? (
                <Link
                  href={`/patients/${item.patient_id}`}
                  className="min-w-0 flex-1 transition-colors hover:text-primary"
                >
                  {content}
                </Link>
              ) : (
                <div className="min-w-0 flex-1">{content}</div>
              )}
              <div className="flex shrink-0 items-center gap-1.5">
                {item.category === "decision" && item.consultation_id && (
                  <ResolveDecisionButton consultationId={item.consultation_id} />
                )}
                <StatusPill label={item.severity} />
              </div>
            </li>
          );
        })}
      </ul>
      {hiddenCount > 0 && (
        <p className="pt-1 text-xs text-muted">{t("criticalPatients.moreFlags").replace("{count}", String(hiddenCount))}</p>
      )}
    </>
  );
}
