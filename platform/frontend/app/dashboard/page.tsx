"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CalendarClock } from "lucide-react";
import { api } from "@/lib/api";
import KpiCard from "@/components/kpi-card";
import StatusPill from "@/components/status-pill";
import AgentBadge from "@/components/agent-badge";

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
        <p className="text-sm text-muted">Here is the summary of overall data</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {data.kpis.map((kpi) => (
          <KpiCard key={kpi.label} kpi={kpi} />
        ))}
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">
                Intelligence
              </div>
              <h2 className="font-bold">Consultations per agent</h2>
            </div>
            <AgentBadge name="AI activity" />
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.agents}>
              <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis tickLine={false} axisLine={false} fontSize={12} width={30} />
              <Tooltip cursor={{ fill: "#EBF3FE" }} />
              <Bar dataKey="consultations" fill="#3683F8" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h2 className="mb-4 font-bold">Agents status</h2>
          <ul className="space-y-3">
            {data.agents.map((agent) => (
              <li key={agent.name} className="flex items-center justify-between">
                <span className="text-sm font-medium">{agent.name}</span>
                <StatusPill label={agent.status} />
              </li>
            ))}
          </ul>
          <div className="mt-5 rounded-xl border border-line/60 p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted">Gemini</span>
              <StatusPill label={data.system.llm} />
            </div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-muted">Model</span>
              <span className="font-semibold">{data.system.model}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
