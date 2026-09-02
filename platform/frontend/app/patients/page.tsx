"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, type PatientSummary } from "@/lib/api";
import { plainCondition } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";

type RiskFilter = "all" | "high" | "medium" | "low";

const RISK_FILTERS: { value: RiskFilter; labelKey: string }[] = [
  { value: "all", labelKey: "patients.filter.all" },
  { value: "high", labelKey: "patients.filter.critical" },
  { value: "medium", labelKey: "patients.filter.moderate" },
  { value: "low", labelKey: "patients.filter.stable" },
];

const RISK_PILL_ACTIVE: Record<RiskFilter, string> = {
  all: "bg-primary text-white",
  high: "bg-danger text-white",
  medium: "bg-warning text-white",
  low: "bg-success text-white",
};

export default function PatientsPage() {
  const { t } = useLanguage();
  const sortByRisk = useSearchParams().get("sort") === "risk";
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const { data: patients, isLoading } = useQuery({
    queryKey: ["patients", sortByRisk ? "risk" : "name"],
    queryFn: () => api.patients(sortByRisk ? "risk" : undefined),
  });

  const counts = useMemo(() => {
    const c: Record<RiskFilter, number> = { all: patients?.length ?? 0, high: 0, medium: 0, low: 0 };
    for (const p of patients ?? []) {
      if (p.risk_level) c[p.risk_level] += 1;
    }
    return c;
  }, [patients]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (patients ?? []).filter((p: PatientSummary) => {
      const matchesRisk = riskFilter === "all" || p.risk_level === riskFilter;
      const matchesSearch =
        !query ||
        p.name.toLowerCase().includes(query) ||
        p.medical_record_number.toLowerCase().includes(query);
      return matchesRisk && matchesSearch;
    });
  }, [patients, search, riskFilter]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("patients.title")}</h1>
        <p className="text-sm text-muted">{t("patients.subtitle")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("patients.filter.searchPlaceholder")}
            className="input pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {RISK_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setRiskFilter(f.value)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                riskFilter === f.value ? RISK_PILL_ACTIVE[f.value] : "bg-surface text-muted hover:text-primary"
              }`}
            >
              {t(f.labelKey)} · {counts[f.value]}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-x-auto !p-0">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line/60 text-left text-xs uppercase tracking-wider text-muted">
              <th className="px-5 py-3.5">{t("patients.table.patient")}</th>
              <th className="px-5 py-3.5">{t("patients.table.mrn")}</th>
              <th className="px-5 py-3.5">{t("patients.table.ageSex")}</th>
              <th className="px-5 py-3.5">{t("patients.table.conditions")}</th>
              <th className="px-5 py-3.5">{t("patients.table.risk")}</th>
              <th className="px-5 py-3.5">{t("patients.table.status")}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-5 py-6 text-muted">
                  {t("patients.loading")}
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-6 text-muted">
                  {t("patients.filter.empty")}
                </td>
              </tr>
            )}
            {filtered.map((patient) => (
              <tr key={patient.id} className="border-b border-line/40 last:border-0 hover:bg-surface/60">
                <td className="px-5 py-3.5">
                  <Link href={`/patients/${patient.id}`} className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-soft text-xs font-bold text-primary">
                      {patient.name.split(" ").map((n) => n[0]).join("")}
                    </span>
                    <span className="font-semibold text-ink hover:text-primary">{patient.name}</span>
                  </Link>
                </td>
                <td className="px-5 py-3.5 text-muted">{patient.medical_record_number}</td>
                <td className="px-5 py-3.5">
                  {patient.age} / {patient.sex}
                </td>
                <td className="max-w-xs px-5 py-3.5 text-sm text-muted">
                  {patient.conditions.slice(0, 3).map((c) => (
                    <div key={c} className="truncate">
                      {plainCondition(c)}
                    </div>
                  ))}
                  {patient.conditions.length > 3 && (
                    <div className="text-xs">
                      {t("criticalPatients.moreFlags").replace("{count}", String(patient.conditions.length - 3))}
                    </div>
                  )}
                </td>
                <td className="px-5 py-3.5">
                  {patient.risk_level && <StatusPill label={patient.risk_level} />}
                </td>
                <td className="px-5 py-3.5">
                  <StatusPill label={patient.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
