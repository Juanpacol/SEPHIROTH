"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Sheet from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { friendlyTestName } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import { useDebounced } from "@/lib/hooks/use-debounced";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-danger/10 text-danger",
  abnormal: "bg-warning/10 text-warning",
  normal: "bg-success/10 text-success",
  unclassified: "bg-surface text-muted",
};

/** `datetime-local` wants local wall time without a zone. */
function localNow(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

/** The server's reason for a 422, which arrives as pydantic's JSON. */
function validationMessage(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 422) return null;
  try {
    const detail = JSON.parse(err.message).detail;
    const msg = Array.isArray(detail) ? detail[0]?.msg : detail;
    return typeof msg === "string" ? msg.replace(/^Value error, /, "") : null;
  } catch {
    return null;
  }
}

/** Record a lab result from the patient chart.
 *
 * Picking a test fills its unit and reference range (both editable); the
 * classification is asked of the server, with the same rules that classify the
 * result once saved, so what the clinician sees before saving is what lands in
 * the review inbox. */
export default function RecordLabSheet({
  patientId,
  open,
  onClose,
}: {
  patientId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const showToast = useToast();
  const queryClient = useQueryClient();

  const [test, setTest] = useState("");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [takenAt, setTakenAt] = useState(localNow);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: catalog } = useQuery({
    queryKey: ["lab-catalog"],
    queryFn: () => api.labCatalog(),
    enabled: open,
    staleTime: Infinity,
  });
  const tests = catalog?.tests ?? [];

  useEffect(() => {
    if (!open) return;
    setTest("");
    setValue("");
    setUnit("");
    setLow("");
    setHigh("");
    setTakenAt(localNow());
    setError(null);
  }, [open]);

  const pick = (name: string) => {
    setTest(name);
    const entry = tests.find((e) => e.test_name === name);
    setUnit(entry?.unit ?? "");
    setLow(entry ? String(entry.reference_low) : "");
    setHigh(entry ? String(entry.reference_high) : "");
    setError(null);
  };

  const numeric = value.trim() !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
  const future = useMemo(
    () => takenAt !== "" && new Date(takenAt).getTime() > Date.now() + 5 * 60_000,
    [takenAt],
  );
  const lowN = low.trim() === "" ? null : Number(low);
  const highN = high.trim() === "" ? null : Number(high);

  const query = useDebounced(test && numeric !== null ? { test, numeric, lowN, highN } : null, 300);
  const preview = useQuery({
    queryKey: ["lab-preview", query],
    queryFn: () =>
      api.previewLab({
        test_name: query!.test,
        value: query!.numeric,
        reference_low: query!.lowN,
        reference_high: query!.highN,
      }),
    enabled: open && query !== null,
    retry: false,
  });
  const previewError = preview.error
    ? (validationMessage(preview.error) ?? t("recordLab.previewFailed"))
    : null;

  const canSave =
    !busy &&
    test !== "" &&
    numeric !== null &&
    takenAt !== "" &&
    !future &&
    preview.isSuccess &&
    !preview.isFetching;

  const save = async () => {
    if (!canSave || numeric === null) return;
    setBusy(true);
    setError(null);
    try {
      const review = await api.recordLab({
        patient_id: patientId,
        test_name: test,
        value: numeric,
        unit,
        taken_at: new Date(takenAt).toISOString(),
        reference_low: lowN,
        reference_high: highN,
      });
      showToast(t(review.created === false ? "recordLab.existed" : "recordLab.saved"));
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["patient-lab-history", patientId],
        }),
        queryClient.invalidateQueries({ queryKey: ["patient", patientId] }),
        queryClient.invalidateQueries({ queryKey: ["results"] }),
      ]);
      onClose();
    } catch (err) {
      setError(validationMessage(err) ?? t("recordLab.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("recordLab.title")}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <div>
          <label htmlFor="rl-test" className="mb-1 block text-sm font-semibold">
            {t("recordLab.test")}
          </label>
          {/* `appearance-none`: WebKit drops a native select's padding, which leaves
              it 24px tall on a phone. The chevron is drawn here instead. */}
          <div className="relative">
            <select
              id="rl-test"
              value={test}
              onChange={(e) => pick(e.target.value)}
              className="input tap min-w-0 appearance-none pr-10"
            >
              <option value="">{t("recordLab.testPlaceholder")}</option>
              {tests.map((e) => (
                <option key={e.test_name} value={e.test_name}>
                  {friendlyTestName(e.test_name, t)}
                </option>
              ))}
            </select>
            <ChevronDown
              aria-hidden="true"
              className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="min-w-0">
            <label htmlFor="rl-value" className="mb-1 block text-sm font-semibold">
              {t("recordLab.value")}
            </label>
            <input
              id="rl-value"
              type="number"
              inputMode="decimal"
              step="any"
              min={0}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="input tap"
            />
          </div>
          <div className="min-w-0">
            <label htmlFor="rl-unit" className="mb-1 block text-sm font-semibold">
              {t("recordLab.unit")}
            </label>
            <input
              id="rl-unit"
              value={unit}
              maxLength={20}
              onChange={(e) => setUnit(e.target.value)}
              className="input tap"
            />
          </div>
        </div>

        <div>
          <label htmlFor="rl-taken" className="mb-1 block text-sm font-semibold">
            {t("recordLab.takenAt")}
          </label>
          <input
            id="rl-taken"
            type="datetime-local"
            value={takenAt}
            max={localNow()}
            onChange={(e) => setTakenAt(e.target.value)}
            className="input tap"
            aria-invalid={future}
            aria-describedby={future ? "rl-future" : undefined}
          />
          {future ? (
            <p id="rl-future" role="alert" className="mt-1 text-xs text-danger">
              {t("recordLab.future")}
            </p>
          ) : null}
        </div>

        <div>
          <div className="grid grid-cols-2 gap-3">
            <div className="min-w-0">
              <label htmlFor="rl-low" className="mb-1 block text-sm font-semibold">
                {t("recordLab.low")}
              </label>
              <input
                id="rl-low"
                type="number"
                inputMode="decimal"
                step="any"
                value={low}
                onChange={(e) => setLow(e.target.value)}
                className="input tap"
              />
            </div>
            <div className="min-w-0">
              <label htmlFor="rl-high" className="mb-1 block text-sm font-semibold">
                {t("recordLab.high")}
              </label>
              <input
                id="rl-high"
                type="number"
                inputMode="decimal"
                step="any"
                value={high}
                onChange={(e) => setHigh(e.target.value)}
                className="input tap"
              />
            </div>
          </div>
          <p className="mt-1 text-xs text-muted">{t("recordLab.rangeHint")}</p>
        </div>

        <div
          className="min-h-[3.5rem] rounded-lg border border-line p-3 text-sm"
          aria-live="polite"
          data-testid="record-lab-preview"
        >
          <div className="mb-1 text-xs font-semibold text-muted">{t("recordLab.classification")}</div>
          {previewError ? (
            <p role="alert" className="text-danger">
              {previewError}
            </p>
          ) : preview.data && query ? (
            <div className="space-y-1">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[preview.data.severity]}`}
              >
                {t(`results.severity.${preview.data.severity}`)}
              </span>
              <p className="text-xs text-muted">{preview.data.reason}</p>
            </div>
          ) : (
            <p className="text-muted">{test && numeric !== null ? t("recordLab.checking") : "—"}</p>
          )}
        </div>

        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={busy} className="btn-ghost tap flex-1">
            {t("recordLab.cancel")}
          </button>
          <button type="submit" disabled={!canSave} className="btn-primary tap flex-1 disabled:opacity-50">
            {busy ? t("recordLab.saving") : t("recordLab.save")}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
