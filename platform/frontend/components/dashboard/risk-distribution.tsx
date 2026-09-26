import { AlertCircle, AlertTriangle, CheckCircle2, type LucideIcon } from "lucide-react";
import { useLanguage } from "@/lib/language";

interface Segment {
  key: "critical" | "moderate" | "stable";
  count: number;
  bar: string;
  icon: LucideIcon;
  iconClass: string;
}

/** Part-to-whole of patients by risk state. Warning and success are hard to
 * tell apart for protan readers, so every segment is also named, iconed and
 * counted in the legend, and a 2px surface gap separates the fills. */
export default function RiskDistribution({
  critical,
  moderate,
  stable,
}: {
  critical: number;
  moderate: number;
  stable: number;
}) {
  const { t } = useLanguage();
  const total = critical + moderate + stable;
  const segments: Segment[] = [
    { key: "critical", count: critical, bar: "bg-danger", icon: AlertTriangle, iconClass: "text-danger" },
    { key: "moderate", count: moderate, bar: "bg-warning", icon: AlertCircle, iconClass: "text-warning" },
    { key: "stable", count: stable, bar: "bg-success", icon: CheckCircle2, iconClass: "text-success" },
  ];
  const summary = segments.map((s) => `${t(`dashboard.stat.${s.key}`)} ${s.count}`).join(", ");

  return (
    <div className="card">
      <div className="text-sm text-muted">{t("dashboard.distribution.title")}</div>
      {total === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("dashboard.distribution.empty")}</p>
      ) : (
        <>
          <div className="mt-3 flex h-3 w-full gap-[2px]" role="img" aria-label={summary}>
            {segments
              .filter((s) => s.count > 0)
              .map((s) => (
                <div
                  key={s.key}
                  className={`${s.bar} h-full rounded-[4px]`}
                  style={{ width: `${(s.count / total) * 100}%`, minWidth: "6px" }}
                />
              ))}
          </div>
          <ul className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-3">
            {segments.map((s) => {
              const Icon = s.icon;
              return (
                <li key={s.key} className="flex items-center gap-1.5 text-sm">
                  <Icon size={14} className={`shrink-0 ${s.iconClass}`} aria-hidden />
                  <span className="text-muted">{t(`dashboard.stat.${s.key}`)}</span>
                  <span className="font-bold text-ink">{s.count}</span>
                  <span className="text-xs text-muted">{Math.round((s.count / total) * 100)}%</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
