"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import StatusPill from "@/components/status-pill";

export default function PatientsPage() {
  const { data: patients, isLoading } = useQuery({
    queryKey: ["patients"],
    queryFn: api.patients,
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">Patients</h1>
        <p className="text-sm text-muted">Detailed overview of patients under AI-assisted care</p>
      </div>

      <div className="card overflow-x-auto !p-0">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line/60 text-left text-xs uppercase tracking-wider text-muted">
              <th className="px-5 py-3.5">Patient</th>
              <th className="px-5 py-3.5">MRN</th>
              <th className="px-5 py-3.5">Age / Sex</th>
              <th className="px-5 py-3.5">Conditions</th>
              <th className="px-5 py-3.5">Risk</th>
              <th className="px-5 py-3.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-5 py-6 text-muted">
                  Loading patients…
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
