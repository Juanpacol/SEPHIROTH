import Link from "next/link";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  ClipboardList,
  FileCheck2,
  FlaskConical,
  HelpCircle,
  type LucideIcon,
  Pill,
  ScanLine,
  ShieldAlert,
  TrendingDown,
} from "lucide-react";
import { api, type DashboardActionGroup, type DashboardActionItem } from "@/lib/api";
import { friendlyTestName, parseInteractionLabel, riskLabel } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import { useToast } from "@/components/ui/toast";

const CATEGORY_ICON: Record<DashboardActionItem["category"], LucideIcon> = {
  alert: ShieldAlert,
  deteriorating: TrendingDown,
  lab: FlaskConical,
  interaction: Pill,
  imaging: ScanLine,
  order: ClipboardList,
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
      const title = riskLabel(item.title, t);
      return item.detail ? `${title} — ${item.detail}` : title;
    }
    case "deteriorating": {
      if (!item.test_name) return t("dashboard.actionItems.deteriorating");
      const test = friendlyTestName(item.test_name, t);
      const extra = (item.worsened_test_count ?? 1) - 1;
      return extra > 0
        ? t("dashboard.actionItems.deterioratingTestMore").replace("{test}", test).replace("{count}", String(extra))
        : t("dashboard.actionItems.deterioratingTest").replace("{test}", test);
    }
    case "lab":
      return t("dashboard.actionItems.lab")
        .replace("{test}", friendlyTestName(item.test_name, t))
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
    case "order":
      return t("dashboard.actionItems.order")
        .replace("{kind}", t(`encounter.orderKind.${item.order_kind}`))
        .replace("{detail}", item.detail ?? "");
    case "followup": {
      const check = t(`dashboard.actionItems.followupCheck.${item.check_key}`);
      return t("dashboard.actionItems.followup")
        .replace("{check}", check)
        .replace("{days}", String(item.days_late ?? 0));
    }
    case "approval": {
      const followupCheck = item.action_type?.match(/^followup_(.+)$/);
      if (followupCheck) {
        const check = t(`dashboard.actionItems.followupCheck.${followupCheck[1]}`);
        return t("dashboard.actionItems.approvalFollowup").replace("{check}", check);
      }
      return t("dashboard.actionItems.approval");
    }
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

function SignalRow({ item }: { item: DashboardActionItem }) {
  const { t } = useLanguage();
  const Icon = CATEGORY_ICON[item.category];
  return (
    <li className="flex min-w-0 items-center gap-2.5">
      <Icon
        size={14}
        className={`shrink-0 ${item.severity === "critical" || item.severity === "high" ? "text-danger" : "text-warning"}`}
      />
      <span className="min-w-0 flex-1 truncate text-xs leading-tight text-muted">{itemText(item, t)}</span>
      {item.category === "decision" && item.consultation_id && (
        <ResolveDecisionButton consultationId={item.consultation_id} />
      )}
    </li>
  );
}

export default function ActionItemsList({
  groups,
  maxVisible,
}: {
  groups: DashboardActionGroup[];
  /** Caps how many patients render — the dashboard needs the worst few at a
   * glance, not the full ranked list, to keep this off a second scroll. */
  maxVisible?: number;
}) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);

  if (groups.length === 0) {
    return <p className="text-sm text-muted">{t("dashboard.actionItems.empty")}</p>;
  }
  const visible = maxVisible && !expanded ? groups.slice(0, maxVisible) : groups;
  const hiddenCount = groups.length - visible.length;

  return (
    <>
      <ul className="divide-y divide-line/60">
        {visible.map((group, i) => (
          <li key={group.patient_id ?? `none-${i}`} className="py-2">
            <div className="flex items-center gap-2">
              {group.patient_id ? (
                <Link
                  href={`/patients/${group.patient_id}`}
                  className="min-w-0 flex-1 truncate text-sm font-semibold leading-tight transition-colors hover:text-primary"
                >
                  {group.patient_name}
                </Link>
              ) : (
                <span className="min-w-0 flex-1 truncate text-sm font-semibold leading-tight">
                  {group.patient_name}
                </span>
              )}
              <StatusPill label={group.severity} />
            </div>
            <ul className="mt-1 space-y-1">
              {group.items.map((item, j) => (
                <SignalRow key={`${item.category}-${j}`} item={item} />
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="pt-1 text-xs font-semibold text-primary hover:underline"
        >
          {t("dashboard.actionItems.showMore").replace("{count}", String(hiddenCount))}
        </button>
      )}
    </>
  );
}
