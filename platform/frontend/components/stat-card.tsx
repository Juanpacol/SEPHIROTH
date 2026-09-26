const toneClass: Record<string, string> = {
  default: "",
  danger: "text-danger",
  warning: "text-warning",
  success: "text-success",
  primary: "text-primary",
};

export default function StatCard({
  label,
  value,
  tone = "default",
  suffix,
  hint,
}: {
  label: string;
  value: string | number | null | undefined;
  tone?: "default" | "danger" | "warning" | "success" | "primary";
  /** Small text right after the number, e.g. the scale ("of 3"). */
  suffix?: string;
  /** One short line under the number explaining how to read it. */
  hint?: string;
}) {
  const empty = value === null || value === undefined;
  return (
    <div className="card">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className={`text-3xl font-extrabold ${toneClass[tone]}`}>{empty ? "—" : value}</span>
        {suffix && !empty && <span className="text-sm font-semibold text-muted">{suffix}</span>}
      </div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}
