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
import DataList, { type Column } from "@/components/ui/data-list";

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

  // Declared once and rendered as both a table and a card stack by `DataList`;
  // `primary` marks what survives on a phone card.
  const columns: Column<PatientSummary>[] = useMemo(
    () => [
      {
        key: "patient",
        header: t("patients.table.patient"),
        primary: true,
        render: (p) => (
          <Link href={`/patients/${p.id}`} className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-soft text-xs font-bold text-primary">
              {p.name
                .split(" ")
                .map((n) => n[0])
                .join("")}
            </span>
            <span className="font-semibold text-ink hover:text-primary">{p.name}</span>
          </Link>
        ),
      },
      {
        key: "mrn",
        header: t("patients.table.mrn"),
        className: "text-muted",
        render: (p) => p.medical_record_number,
      },
      {
        key: "ageSex",
        header: t("patients.table.ageSex"),
        render: (p) => `${p.age} / ${p.sex}`,
      },
      {
        key: "conditions",
        header: t("patients.table.conditions"),
        // Three truncated lines read fine in a table cell and badly in a
        // two-column card grid, so the card shape drops them; the patient
        // page is one tap away and shows all of them.
        desktopOnly: true,
        className: "max-w-xs text-sm text-muted",
        render: (p) => (
          <>
            {p.conditions.slice(0, 3).map((c) => (
              <div key={c} className="truncate">
                {plainCondition(c)}
              </div>
            ))}
            {p.conditions.length > 3 && (
              <div className="text-xs">
                {t("criticalPatients.moreFlags").replace("{count}", String(p.conditions.length - 3))}
              </div>
            )}
          </>
        ),
      },
      {
        key: "risk",
        header: t("patients.table.risk"),
        render: (p) => (p.risk_level ? <StatusPill label={p.risk_level} /> : null),
      },
      {
        key: "status",
        header: t("patients.table.status"),
        render: (p) => <StatusPill label={p.status} />,
      },
    ],
    [t],
  );

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

      <DataList
        items={filtered}
        rowKey={(p) => p.id}
        onRowHref={(p) => `/patients/${p.id}`}
        isLoading={isLoading}
        loadingLabel={t("patients.loading")}
        emptyLabel={t("patients.filter.empty")}
        caption={t("patients.title")}
        columns={columns}
      />
    </div>
  );
}
