"use client";

import { useState } from "react";

export default function CitationGuardToggle() {
  const [mode, setMode] = useState<"raw" | "guarded">("raw");

  return (
    <div className="card">
      <div
        role="radiogroup"
        aria-label="Raw model output vs after Citation Guard"
        className="mb-4 inline-flex items-center gap-0.5 rounded-full bg-primary-soft p-1"
      >
        {(["raw", "guarded"] as const).map((value) => (
          <button
            key={value}
            role="radio"
            aria-checked={mode === value}
            onClick={() => setMode(value)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              mode === value ? "bg-card text-primary shadow-sm" : "text-muted hover:text-primary"
            }`}
          >
            {value === "raw" ? "Raw model output" : "After Citation Guard"}
          </button>
        ))}
      </div>

      {mode === "raw" ? (
        <p className="text-sm" hidden={mode !== "raw"}>
          Target A1C is &lt;7% [ADA Standards of Care, 2024]{" "}
          <span className="rounded bg-danger/10 px-1 text-danger">[UpToDate Diabetes Review, 2023]</span>.
          Current value (8.1%) is above goal.
        </p>
      ) : (
        <div hidden={mode !== "guarded"}>
          <p className="text-sm">
            Target A1C is &lt;7% [ADA Standards of Care, 2024] [unverified — removed]. Current value
            (8.1%) is above goal.
          </p>
          <p className="mt-2 text-xs text-muted">
            1 citation removed — no matching source in the retrieved set.
          </p>
        </div>
      )}
    </div>
  );
}
