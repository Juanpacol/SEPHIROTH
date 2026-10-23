"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { initialsOf } from "@/lib/initials";
import FilterTabs from "@/components/ui/filter-tabs";
import PageHeader from "@/components/ui/page-header";
import { api, type PatientSummary } from "@/lib/api";
import { plainCondition } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import DataList, { type Column } from "@/components/ui/data-list";

type RiskFilter = "all" | "high" | "medium" | "low";

const RISK_FILTERS: { value: RiskFilter; labelKey: string; dot?: string }[] = [
  { value: "all", labelKey: "patients.filter.all" },
  { value: "high", labelKey: "patients.filter.critical", dot: "bg-danger" },
  { value: "medium", labelKey: "patients.filter.moderate", dot: "bg-warning" },
  { value: "low", labelKey: "patients.filter.stable", dot: "bg-success" },
];

const RISK_ACCENT: Record<string, string> = { high: "bg-danger", medium: "bg-warning" };

export default function PatientsPage() {
  const { t } = useLanguage();
  // Most urgent first unless the URL asks for names (`?sort=name`).
  const sortByRisk = useSearchParams().get("sort") !== "name";
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

  // Declared once; DataList generates both the table and the phone cards from
  // this, so a column can't exist in one shape and not the other.
  const columns: Column<PatientSummary>[] = [
    {
      key: "patient",
      header: t("patients.table.patient"),
      primary: true,
      render: (p) => (
        <span className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-soft font-mono text-[11px] font-semibold tracking-wider text-primary-ink">
            {initialsOf(p.name)}
          </span>
          <span className="min-w-0">
            <span className="block truncate font-semibold text-ink">{p.name}</span>
            <span className="block truncate font-mono text-[11px] tracking-wide text-muted">
              {p.medical_record_number} · {p.age} / {p.sex}
            </span>
          </span>
        </span>
      ),
    },
    {
      key: "risk",
      header: t("patients.table.risk"),
      primary: true,
      render: (p) => (p.risk_level ? <StatusPill label={p.risk_level} /> : null),
    },
    {
      // Two lines at most: a third is what made rows uneven, and the rest are one tap away on the chart.
      key: "conditions",
      header: t("patients.table.conditions"),
      className: "max-w-sm text-muted",
      render: (p) => (
        <>
          {p.conditions.slice(0, 2).map((c) => (
            <div key={c} className="truncate">
              {plainCondition(c)}
            </div>
          ))}
          {p.conditions.length > 2 && (
            <div className="font-mono text-[11px]">
              {t("patients.table.moreConditions").replace("{count}", String(p.conditions.length - 2))}
            </div>
          )}
        </>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow={t("patients.eyebrow")}
        title={t("patients.title")}
        subtitle={t("patients.subtitle")}
      />

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <FilterTabs
          label={t("patients.filter.group")}
          value={riskFilter}
          onChange={setRiskFilter}
          tabs={RISK_FILTERS.map((f) => ({
            value: f.value,
            label: t(f.labelKey),
            count: counts[f.value],
            dot: f.dot,
          }))}
        />
        <div className="relative w-full sm:w-72">
          <Search
            size={14}
            strokeWidth={1.5}
            className="pointer-events-none absolute left-0 top-1/2 -translate-y-1/2 text-muted"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("patients.filter.searchPlaceholder")}
            aria-label={t("patients.filter.searchPlaceholder")}
            className="w-full border-0 border-b border-line/60 bg-transparent py-2 pl-6 pr-1 text-sm text-ink transition-colors duration-normal placeholder:text-muted focus:border-primary-ink focus-visible:!outline-none"
          />
        </div>
      </div>

      <DataList
        items={filtered}
        columns={columns}
        rowKey={(p) => p.id}
        onRowHref={(p) => `/patients/${p.id}`}
        rowAccent={(p) => (p.risk_level ? RISK_ACCENT[p.risk_level] : null)}
        isLoading={isLoading}
        loadingLabel={t("patients.loading")}
        emptyLabel={t("patients.filter.empty")}
        caption={t("patients.title")}
      />
    </div>
  );
}
