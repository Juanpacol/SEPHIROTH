import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import type { CriticalPatient } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";

export default function CriticalPatientsList({
  patients,
  maxVisible,
}: {
  patients: CriticalPatient[];
  /** Caps how many rows render before falling back to the "view all" link
   * above this list — the dashboard needs a glance, not a full roster. */
  maxVisible?: number;
}) {
  const { t } = useLanguage();
  if (patients.length === 0) {
    return <p className="text-sm text-muted">{t("criticalPatients.empty")}</p>;
  }
  const visible = maxVisible ? patients.slice(0, maxVisible) : patients;
  const hiddenCount = patients.length - visible.length;

  return (
    <>
      <ul className="divide-y divide-line/60">
        {visible.map((p) => (
          <li key={p.id}>
            <Link
              href={`/patients/${p.id}`}
              className="flex items-center justify-between gap-3 py-1.5 transition-colors hover:bg-primary-soft/40"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <AlertTriangle
                  size={14}
                  className={p.risk_level === "high" ? "shrink-0 text-danger" : "shrink-0 text-warning"}
                />
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold leading-tight">{p.name}</div>
                  {p.top_flag && (
                    <div className="truncate text-xs leading-tight text-muted">
                      {p.top_flag}
                      {p.flag_count > 1 &&
                        ` · ${t("criticalPatients.moreFlags").replace("{count}", String(p.flag_count - 1))}`}
                    </div>
                  )}
                </div>
              </div>
              <StatusPill label={`${p.risk_level} risk`} />
            </Link>
          </li>
        ))}
      </ul>
      {hiddenCount > 0 && (
        <p className="pt-1 text-xs text-muted">
          {t("criticalPatients.moreFlags").replace("{count}", String(hiddenCount))}
        </p>
      )}
    </>
  );
}
