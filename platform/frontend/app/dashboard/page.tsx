"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import CriticalPatientsList from "@/components/critical-patients-list";

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboardStats,
    refetchInterval: 30_000,
  });
  const { data: agenda } = useQuery({
    queryKey: ["agenda", "today"],
    queryFn: api.agendaToday,
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="text-muted">Loading overview…</div>;
  if (error || !data)
    return (
      <div className="card text-danger">
        Backend unreachable — start it with{" "}
        <code className="rounded bg-surface px-1">
          PYTHONPATH=.:platform uvicorn api.main:app
        </code>
      </div>
    );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-extrabold">Overview</h1>
        <p className="text-sm text-muted">Who needs attention today</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="card">
          <div className="text-sm text-muted">High risk</div>
          <div className="mt-1 text-3xl font-extrabold text-danger">{data.critical_count}</div>
        </div>
        <div className="card">
          <div className="text-sm text-muted">At risk (high + medium)</div>
          <div className="mt-1 text-3xl font-extrabold">{data.at_risk_count}</div>
        </div>
      </div>

      <div className="card">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <ShieldAlert size={16} className="text-primary" /> Critical patients
          </h2>
          <Link href="/patients?sort=risk" className="text-sm font-semibold text-primary">
            View all →
          </Link>
        </div>
        <CriticalPatientsList patients={data.critical_patients} />
      </div>

      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <CalendarClock size={16} className="text-primary" /> Today&apos;s agenda
          </h2>
          <Link href="/schedule" className="text-sm font-semibold text-primary">
            View schedule →
          </Link>
        </div>
        {!agenda || agenda.count === 0 ? (
          <p className="text-sm text-muted">No appointments today.</p>
        ) : (
          <>
            <p className="mb-2 text-sm text-muted">
              {agenda.count} appointment{agenda.count > 1 ? "s" : ""}
              {agenda.next_at &&
                ` · Next: ${new Date(agenda.next_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
            </p>
            <ul className="space-y-1.5 text-sm">
              {agenda.items.slice(0, 4).map((item) => (
                <li key={item.id} className="flex justify-between">
                  <span className="font-medium">{item.patient_name}</span>
                  <span className="text-muted">
                    {new Date(item.start_at + "Z").toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
