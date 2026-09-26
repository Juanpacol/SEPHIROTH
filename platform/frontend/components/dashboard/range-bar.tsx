import type { RiskFactor } from "@/lib/api";

function fired(factor: RiskFactor): boolean {
  if (factor.comparator === ">") return factor.value > factor.threshold;
  if (factor.comparator === "<") return factor.value < factor.threshold;
  return factor.value >= factor.threshold;
}

/** Where the value sits against the rule's threshold. The side past the
 * threshold is tinted, the threshold is a tick, the value is a dot — and the
 * same facts are always written out beside it, so colour never carries the
 * meaning alone (SPEC-031 B-8). */
export default function RangeBar({ factor, text }: { factor: RiskFactor; text: string }) {
  const low = Math.min(factor.value, factor.threshold);
  const high = Math.max(factor.value, factor.threshold);
  const pad = (high - low || Math.abs(high) || 1) * 0.6;
  const min = Math.max(0, low - pad);
  const max = high + pad;
  const pos = (v: number) => `${(((v - min) / (max - min)) * 100).toFixed(1)}%`;
  const upward = factor.comparator !== "<";
  const isFiring = fired(factor);

  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="relative h-1.5 w-20 shrink-0 rounded-full bg-line/70" aria-hidden>
        <div
          className="absolute inset-y-0 rounded-full bg-danger/25"
          style={upward ? { left: pos(factor.threshold), right: 0 } : { left: 0, right: `calc(100% - ${pos(factor.threshold)})` }}
        />
        <div className="absolute -inset-y-0.5 w-px bg-ink/60" style={{ left: pos(factor.threshold) }} />
        <div
          className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card ${
            isFiring ? "bg-danger" : "bg-ink/50"
          }`}
          style={{ left: pos(factor.value) }}
        />
      </div>
      <span className="min-w-0 text-[11px] leading-tight text-muted sm:truncate">{text}</span>
    </div>
  );
}
