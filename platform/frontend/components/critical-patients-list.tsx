import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import type { CriticalPatient } from "@/lib/api";
import StatusPill from "@/components/status-pill";

export default function CriticalPatientsList({ patients }: { patients: CriticalPatient[] }) {
  if (patients.length === 0) {
    return <p className="text-sm text-muted">No high or medium-risk patients right now.</p>;
  }

  return (
    <ul className="divide-y divide-line/60">
      {patients.map((p) => (
        <li key={p.id}>
          <Link
            href={`/patients/${p.id}`}
            className="flex items-center justify-between gap-3 py-3 transition-colors hover:bg-primary-soft/40"
          >
            <div className="flex min-w-0 items-center gap-3">
              <AlertTriangle
                size={16}
                className={p.risk_level === "high" ? "shrink-0 text-danger" : "shrink-0 text-warning"}
              />
              <div className="min-w-0">
                <div className="font-semibold">{p.name}</div>
                {p.top_flag && (
                  <div className="truncate text-sm text-muted">
                    {p.top_flag}
                    {p.flag_count > 1 && ` · +${p.flag_count - 1} more`}
                  </div>
                )}
              </div>
            </div>
            <StatusPill label={`${p.risk_level} risk`} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
