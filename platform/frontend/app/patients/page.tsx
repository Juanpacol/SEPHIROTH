"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";

export default function PatientsPage() {
  const { t } = useLanguage();
  const sortByRisk = useSearchParams().get("sort") === "risk";
  const { data: patients, isLoading } = useQuery({
    queryKey: ["patients", sortByRisk ? "risk" : "name"],
    queryFn: () => api.patients(sortByRisk ? "risk" : undefined),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("patients.title")}</h1>
        <p className="text-sm text-muted">{t("patients.subtitle")}</p>
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
            {patients?.map((patient) => (
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
                <td className="px-5 py-3.5">
                  <div className="flex flex-wrap gap-1">
                    {patient.conditions.map((c) => (
                      <span key={c} className="rounded-full bg-surface px-2 py-0.5 text-xs">
                        {c}
                      </span>
                    ))}
                  </div>
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
