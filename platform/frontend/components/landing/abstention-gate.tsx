"use client";

import { useState } from "react";

const THRESHOLD = 50;

export default function AbstentionGate() {
  const [value, setValue] = useState(75);
  const belowThreshold = value < THRESHOLD;

  return (
    <div className="card">
      <label htmlFor="evidence-strength" className="mb-2 block text-sm font-semibold">
        Evidence strength
      </label>
      <div className="relative mb-4">
        <input
          id="evidence-strength"
          type="range"
          min={0}
          max={100}
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
          aria-valuetext={belowThreshold ? "Below the abstention threshold" : "Above the abstention threshold"}
          className="w-full accent-primary"
        />
        <div className="pointer-events-none absolute -top-1 h-3 w-px bg-danger/60" style={{ left: `${THRESHOLD}%` }} />
      </div>

      <div role="region" aria-live="polite">
        {belowThreshold ? (
          <div className="card border border-warning/40 bg-warning/10">
            <p className="text-sm font-semibold">
              I don&apos;t have sufficient evidence to answer this safely.
            </p>
            <p className="mt-1 text-sm text-muted">
              Here&apos;s what I&apos;d need: a retrieved guideline or study directly addressing this
              question, or lab values confirming the specific claim.
            </p>
          </div>
        ) : (
          <div className="card border border-primary/30 ai-ring">
            <p className="text-sm">
              Target A1C is &lt;7% [ADA Standards of Care, 2024]. Current value (8.1%) is above goal.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
