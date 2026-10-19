"use client";

import { type PortalLab } from "@/lib/api";
import { friendlyTestName } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import { labExplanation, labRange, labValue } from "@/lib/portal-labs";

const TONE: Record<PortalLab["standing"], string> = {
  inside: "text-success",
  outside: "text-warning",
  needs_attention: "text-danger",
  unknown: "text-ink",
};

/** One communicated lab result, for the patient. Used by the list and by the
 * detail of a result, so both say the same thing the same way. */
export default function LabResultCard({ lab, showMessage = true }: { lab: PortalLab; showMessage?: boolean }) {
  const { t, lang } = useLanguage();
  const range = labRange(lab);

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="min-w-0 text-sm font-semibold">{friendlyTestName(lab.test_name, t)}</h2>
        <span className={`shrink-0 text-base font-bold ${TONE[lab.standing]}`}>{labValue(lab)}</span>
      </div>
      <div className="text-xs text-muted">
        {t("portal.labs.taken").replace("{date}", new Date(lab.taken_at).toLocaleDateString(lang))}
        {range ? (
          <>
            <span aria-hidden="true"> · </span>
            <span>{t("portal.labs.range")}</span>
            <span className="whitespace-nowrap">{range}</span>
          </>
        ) : null}
      </div>
      <p className="text-sm">{labExplanation(lab, t)}</p>
      {showMessage && lab.message ? (
        <div className="rounded-xl border border-primary/20 bg-primary-soft/60 p-3">
          <div className="mb-1 text-xs font-semibold uppercase text-primary">{t("portal.results.fromClinician")}</div>
          <p className="whitespace-pre-wrap text-sm">{lab.message}</p>
        </div>
      ) : null}
    </div>
  );
}
