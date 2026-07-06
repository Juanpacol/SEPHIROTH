const styles: Record<string, string> = {
  active: "bg-success/10 text-success",
  ready: "bg-success/10 text-success",
  online: "bg-success/10 text-success",
  offline: "bg-danger/10 text-danger",
  major: "bg-danger/10 text-danger",
  moderate: "bg-warning/10 text-warning",
  // Risk levels (rule-based risk engine)
  high: "bg-danger/10 text-danger",
  medium: "bg-warning/10 text-warning",
  low: "bg-success/10 text-success",
  "high risk": "bg-danger/10 text-danger",
  "medium risk": "bg-warning/10 text-warning",
  "low risk": "bg-success/10 text-success",
};

// Clinical severity — a pulsing dot draws the eye to HIGH risk the way a
// monitor alarm would; medium gets a steady glow, low stays calm/static.
const riskDots: Record<string, string> = {
  high: "bg-danger animate-pulse shadow-[0_0_0_3px_rgba(239,68,68,0.25)]",
  "high risk": "bg-danger animate-pulse shadow-[0_0_0_3px_rgba(239,68,68,0.25)]",
  medium: "bg-warning shadow-[0_0_0_3px_rgba(245,158,11,0.2)]",
  "medium risk": "bg-warning shadow-[0_0_0_3px_rgba(245,158,11,0.2)]",
  low: "bg-success",
  "low risk": "bg-success",
};

export default function StatusPill({ label }: { label: string }) {
  const key = label.toLowerCase();
  const style = styles[key] ?? "bg-primary-soft text-primary";
  const dot = riskDots[key];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${style}`}
    >
      {dot && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} aria-hidden />}
      {label}
    </span>
  );
}
