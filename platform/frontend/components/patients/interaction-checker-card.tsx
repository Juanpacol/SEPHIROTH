"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";

/** Lets a clinician check a candidate medication against the patient's
 * current list before adding it — reuses the same `/api/medical/drugs/check`
 * tool the Risk Flags card's drug-interaction flags are already derived
 * from, but on demand for a med that isn't in the record yet. Explicit
 * button, not on-mount: this calls an MCP tool, don't fire it for free. */
export default function InteractionCheckerCard({ medications }: { medications: string[] }) {
  const { t } = useLanguage();
  const [candidate, setCandidate] = useState("");

  const check = useMutation({
    mutationFn: (med: string) => api.checkDrugInteractions([...medications, med]),
  });

  const relevant = check.data?.interactions.filter((i) =>
    i.pair.some((name) => name.toLowerCase() === candidate.trim().toLowerCase())
  );

  return (
    <div className="card">
      <h2 className="mb-1 font-bold">{t("patientDetail.interactionChecker.title")}</h2>
      <p className="mb-3 text-sm text-muted">
        {medications.length
          ? t("patientDetail.interactionChecker.subtitleWithMeds")
          : t("patientDetail.interactionChecker.subtitleEmpty")}
      </p>
      <div className="flex gap-2">
        <input
          value={candidate}
          onChange={(e) => setCandidate(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && candidate.trim() && check.mutate(candidate.trim())}
          placeholder={t("patientDetail.interactionChecker.placeholder")}
          className="input flex-1"
        />
        <button
          onClick={() => candidate.trim() && check.mutate(candidate.trim())}
          disabled={!candidate.trim() || check.isPending}
          className="btn-primary shrink-0"
        >
          <Search size={15} />
          {check.isPending
            ? t("patientDetail.interactionChecker.checking")
            : t("patientDetail.interactionChecker.check")}
        </button>
      </div>

      {check.isSuccess && (
        <div className="mt-4">
          {!relevant || relevant.length === 0 ? (
            <p className="text-sm text-success">{t("patientDetail.interactionChecker.none")}</p>
          ) : (
            <ul className="space-y-3">
              {relevant.map((interaction, i) => {
                // Name which drug is already on the patient's own list vs.
                // the one being checked, so the sentence reads as "this
                // patient, specifically" instead of a generic drug-pair
                // lookup — the candidate is whichever side of the pair
                // isn't already in `medications`.
                const candidateLower = candidate.trim().toLowerCase();
                const existingDrug =
                  interaction.pair.find((name) => name.toLowerCase() !== candidateLower) ?? interaction.pair[0];
                const candidateDrug =
                  interaction.pair.find((name) => name.toLowerCase() === candidateLower) ?? candidate.trim();
                return (
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
                      <div className="text-xs text-ink/80">
                        {t("patientDetail.interactionChecker.impact")
                          .replace("{existing}", existingDrug)
                          .replace("{candidate}", candidateDrug)
                          .replace("{effect}", interaction.effect.replace(/\.$/, "").toLowerCase())}
                      </div>
                      <div className="text-xs text-muted">
                        {t("patientDetail.interactionChecker.whatToDo").replace(
                          "{recommendation}",
                          interaction.recommendation
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-3 text-xs text-muted">{check.data.disclaimer}</p>
        </div>
      )}

      {check.isError && (
        <p className="mt-3 text-sm text-danger">{t("patientDetail.interactionChecker.error")}</p>
      )}
    </div>
  );
}
