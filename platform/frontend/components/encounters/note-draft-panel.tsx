"use client";

/** Ask the model to sort free text into SOAP sections.
 *
 * The draft is shown **beside** the note, never written into it. Applying it is
 * a separate button the clinician presses, which is the UI half of ADR-016: a
 * model's text does not reach the record before a human has looked at it.
 *
 * Sections the model appears to have written rather than reorganised are marked.
 * A small local model does not reliably obey "do not add information" — verified
 * during this phase — so the panel aims the clinician's attention rather than
 * presenting four sections as equally faithful.
 */

import { useState } from "react";
import { AlertTriangle, Sparkles } from "lucide-react";

import { api, type NoteDraft } from "@/lib/api";
import { useLanguage } from "@/lib/language";

const SECTIONS = ["subjective", "objective", "assessment", "plan"] as const;
type Section = (typeof SECTIONS)[number];

interface Props {
  encounterId: string;
  specialty: string;
  disabled?: boolean;
  onApply: (draft: NoteDraft) => void;
}

export default function NoteDraftPanel({ encounterId, specialty, disabled, onApply }: Props) {
  const { t } = useLanguage();
  const [transcript, setTranscript] = useState("");
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function requestDraft() {
    if (!transcript.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await api.draftEncounterNote(encounterId, transcript, specialty));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const added = new Set(draft?.added_content ?? []);

  return (
    <section className="card flex flex-col gap-3">
      <header className="flex items-center gap-2">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-r from-sephiroth-start to-sephiroth-end text-white">
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
        </span>
        <h2 className="text-sm font-semibold">{t("encounter.draft.title")}</h2>
      </header>

      <p className="text-xs text-ink/60">{t("encounter.draft.help")}</p>

      <textarea
        rows={5}
        value={transcript}
        disabled={disabled}
        onChange={(event) => setTranscript(event.target.value)}
        placeholder={t("encounter.draft.placeholder")}
        className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm disabled:opacity-60"
      />

      <button
        type="button"
        onClick={requestDraft}
        disabled={disabled || busy || !transcript.trim()}
        className="btn-primary tap self-start disabled:opacity-50"
      >
        {busy ? t("encounter.draft.working") : t("encounter.draft.action")}
      </button>

      {error ? <p className="text-xs text-danger">{error}</p> : null}

      {draft ? (
        <div className="flex flex-col gap-3 border-t border-border pt-3">
          {draft.source === "template" ? (
            // Never presented as a model draft: it is the clinician's own text
            // back under headings, and saying otherwise would be a small lie
            // with a large consequence.
            <p className="rounded-lg bg-surface px-3 py-2 text-xs text-ink/70">
              {t("encounter.draft.degraded")}
            </p>
          ) : (
            <p className="text-xs text-ink/50">
              {t("encounter.draft.model")}: {draft.model}
            </p>
          )}

          {added.size > 0 ? (
            <p className="flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-xs text-ink">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
              <span>{t("encounter.draft.addedContent")}</span>
            </p>
          ) : null}

          <dl className="flex flex-col gap-2">
            {SECTIONS.map((section) => (
              <div key={section}>
                <dt className="flex items-center gap-1.5 text-xs font-medium text-ink/70">
                  {t(`encounter.section.${section}`)}
                  {added.has(section) ? (
                    <span className="rounded bg-warning/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-ink">
                      {t("encounter.draft.addedBadge")}
                    </span>
                  ) : null}
                </dt>
                <dd className="whitespace-pre-wrap text-sm text-ink/80">
                  {draft[section as Section] || <span className="text-ink/40">—</span>}
                </dd>
              </div>
            ))}
          </dl>

          <button
            type="button"
            onClick={() => onApply(draft)}
            disabled={disabled}
            className="btn-secondary tap self-start"
          >
            {t("encounter.draft.apply")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
