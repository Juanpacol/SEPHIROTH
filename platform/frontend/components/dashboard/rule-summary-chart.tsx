import Link from "next/link";
import { useState } from "react";
import { AlertCircle, AlertTriangle, ChevronDown } from "lucide-react";
import type { DashboardRuleSummary } from "@/lib/api";
import { riskLabel } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";

const MAX_VISIBLE = 6;

/** Patients per active problem, across every patient (SPEC-031 B-13, B-14).
 * Bars are proportional to the largest one; the count is always written out,
 * and severity carries an icon as well as a colour. Each bar opens its own
 * patient list rather than filtering the capped action list (NG-7). */
export default function RuleSummaryChart({ summary }: { summary: DashboardRuleSummary }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  if (summary.rules.length === 0) {
    return <p className="text-sm text-muted">{t("dashboard.ruleSummary.empty")}</p>;
  }
  const max = Math.max(...summary.rules.map((rule) => rule.count));
  const visible = showAll ? summary.rules : summary.rules.slice(0, MAX_VISIBLE);
  const hidden = summary.rules.length - visible.length;

  return (
    <>
      <ul className="space-y-1">
        {visible.map((rule) => {
          const expanded = open === rule.rule_code;
          const high = rule.severity === "high";
          const Icon = high ? AlertTriangle : AlertCircle;
          const label = riskLabel(rule.label, t);
          const countText =
            rule.count === 1
              ? t("dashboard.ruleSummary.onePatient")
              : t("dashboard.ruleSummary.patients").replace("{count}", String(rule.count));
          return (
            <li key={rule.rule_code}>
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : rule.rule_code)}
                aria-expanded={expanded}
                aria-label={`${label}: ${countText}`}
                className="tap flex w-full min-w-0 flex-col gap-1 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-primary-soft/40"
              >
                <span className="flex w-full min-w-0 items-center gap-2 text-sm">
                  <Icon size={14} className={`shrink-0 ${high ? "text-danger" : "text-warning"}`} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                  <span className="shrink-0 font-bold text-ink">{rule.count}</span>
                  <ChevronDown
                    size={14}
                    aria-hidden
                    className={`shrink-0 text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
                  />
                </span>
                <span className="block h-2 w-full rounded-[4px] bg-line/50" aria-hidden>
                  <span
                    className={`block h-full rounded-[4px] ${high ? "bg-danger" : "bg-warning"}`}
                    style={{ width: `${(rule.count / max) * 100}%`, minWidth: "6px" }}
                  />
                </span>
              </button>
              {expanded && (
                <ul className="mb-1 ml-6 mt-0.5 divide-y divide-line/60">
                  {rule.patients.map((patient) => (
                    <li key={patient.id}>
                      <Link
                        href={`/patients/${patient.id}`}
                        className="tap flex min-w-0 items-center justify-between gap-2 py-1 text-sm transition-colors hover:text-primary"
                      >
                        <span className="min-w-0 truncate">{patient.name}</span>
                        <span className="shrink-0 whitespace-nowrap">
                          <StatusPill label={`${patient.risk_level} risk`} />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="tap pt-1 text-xs font-semibold text-primary hover:underline"
        >
          {t("dashboard.ruleSummary.showMore").replace("{count}", String(hidden))}
        </button>
      )}
    </>
  );
}
