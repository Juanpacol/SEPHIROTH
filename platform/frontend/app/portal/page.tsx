"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";

export default function PortalHomePage() {
  const user = useUser();

  const { data: me } = useQuery({ queryKey: ["portal", "me"], queryFn: api.portalMe });
  const { data: appointments } = useQuery({
    queryKey: ["portal", "appointments"],
    queryFn: () => api.listAppointments(),
  });
  const { data: shares } = useQuery({ queryKey: ["portal", "shares"], queryFn: () => api.listShares() });

  const upcoming = (appointments ?? []).filter((a) => a.status === "booked").slice(0, 3);
  const unreadResults = (shares ?? []).filter((s) => !s.viewed_at);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold">Welcome, {user?.name?.split(" ")[0] ?? "there"}</h1>
        {me && (
          <p className="text-sm text-muted">
            {me.name} · Age {me.age}
          </p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <CalendarDays size={16} className="text-primary" /> Upcoming appointments
          </div>
          {upcoming.length === 0 && <p className="text-sm text-muted">No upcoming appointments.</p>}
          <ul className="space-y-2">
            {upcoming.map((a) => (
              <li key={a.id} className="text-sm">
                <span className="font-semibold">
                  {new Date(a.start_at + "Z").toLocaleString([], {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                {a.reason && <span className="text-muted"> — {a.reason}</span>}
              </li>
            ))}
          </ul>
          <Link href="/portal/appointments" className="mt-3 inline-block text-sm font-semibold text-primary">
            View all appointments →
          </Link>
        </div>

        <div className="card">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <FileText size={16} className="text-primary" /> Results
          </div>
          <p className="text-sm text-muted">
            {unreadResults.length > 0
              ? `${unreadResults.length} new result${unreadResults.length > 1 ? "s" : ""} from your clinician.`
              : "No new results."}
          </p>
          <Link href="/portal/results" className="mt-3 inline-block text-sm font-semibold text-primary">
            View results →
          </Link>
        </div>
      </div>

      {me && (
        <div className="card">
          <div className="mb-3 text-sm font-semibold">Your health summary</div>
          <div className="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <div className="text-xs font-semibold uppercase text-muted">Conditions</div>
              <p>{me.conditions.length ? me.conditions.join(", ") : "None on file"}</p>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase text-muted">Medications</div>
              <p>{me.medications.length ? me.medications.join(", ") : "None on file"}</p>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase text-muted">Allergies</div>
              <p>{me.allergies.length ? me.allergies.join(", ") : "None on file"}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
