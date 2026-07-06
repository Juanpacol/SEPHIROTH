import { TrendingDown, TrendingUp } from "lucide-react";
import type { Kpi } from "@/lib/api";

export default function KpiCard({ kpi }: { kpi: Kpi }) {
  const up = kpi.trend === "up";
  return (
    <div className="card">
      <div className="text-sm text-muted">{kpi.label}</div>
      <div className="mt-2 flex items-end justify-between">
        <span className="text-3xl font-extrabold">{kpi.value}</span>
        <span
          className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
            up ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
          }`}
        >
          {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {kpi.delta}
        </span>
      </div>
    </div>
  );
}
