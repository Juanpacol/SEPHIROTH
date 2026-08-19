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
}: {
  label: string;
  value: string | number | null | undefined;
  tone?: "default" | "danger" | "warning" | "success" | "primary";
}) {
  return (
    <div className="card">
      <div className="text-sm text-muted">{label}</div>
      <div className={`mt-1 text-3xl font-extrabold ${toneClass[tone]}`}>
        {value === null || value === undefined ? "—" : value}
      </div>
    </div>
  );
}
