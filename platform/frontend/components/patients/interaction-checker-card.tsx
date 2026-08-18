"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Search } from "lucide-react";
import { api } from "@/lib/api";
import StatusPill from "@/components/status-pill";

/** Lets a clinician check a candidate medication against the patient's
 * current list before adding it — reuses the same `/api/medical/drugs/check`
 * tool the Risk Flags card's drug-interaction flags are already derived
 * from, but on demand for a med that isn't in the record yet. Explicit
 * button, not on-mount: this calls an MCP tool, don't fire it for free. */
export default function InteractionCheckerCard({ medications }: { medications: string[] }) {
  const [candidate, setCandidate] = useState("");

  const check = useMutation({
    mutationFn: (med: string) => api.checkDrugInteractions([...medications, med]),
  });

  const relevant = check.data?.interactions.filter((i) =>
    i.pair.some((name) => name.toLowerCase() === candidate.trim().toLowerCase())
  );

  return (
    <div className="card">
      <h2 className="mb-1 font-bold">Interaction Checker</h2>
      <p className="mb-3 text-sm text-muted">
        Check a medication against {medications.length ? "this patient's current list" : "the record"}.
      </p>
      <div className="flex gap-2">
        <input
          value={candidate}
          onChange={(e) => setCandidate(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && candidate.trim() && check.mutate(candidate.trim())}
          placeholder="e.g. ibuprofen"
          className="input flex-1"
        />
        <button
          onClick={() => candidate.trim() && check.mutate(candidate.trim())}
          disabled={!candidate.trim() || check.isPending}
          className="btn-primary shrink-0"
        >
          <Search size={15} />
          {check.isPending ? "Checking…" : "Check"}
        </button>
      </div>

      {check.isSuccess && (
        <div className="mt-4">
          {!relevant || relevant.length === 0 ? (
            <p className="text-sm text-success">No known interaction with the current list.</p>
          ) : (
            <ul className="space-y-2.5">
              {relevant.map((interaction, i) => (
                <li key={i} className="flex items-start gap-2 rounded-lg p-1.5 text-sm">
                  <AlertTriangle
                    size={15}
                    className={`mt-0.5 shrink-0 ${interaction.severity === "major" ? "text-danger" : "text-warning"}`}
                  />
                  <div>
                    <div className="flex items-center gap-2 font-semibold">
                      {interaction.pair.join(" + ")}
                      <StatusPill label={interaction.severity} />
                    </div>
                    <div className="text-xs text-muted">{interaction.effect}</div>
                    <div className="text-xs text-muted">{interaction.recommendation}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-muted">{check.data.disclaimer}</p>
        </div>
      )}

      {check.isError && <p className="mt-3 text-sm text-danger">Could not reach the interaction checker.</p>}
    </div>
  );
}
