/** Plain-language helpers for backend-authored clinical strings that read
 * too formally for a quick clinical glance -- shared between the dashboard
 * action-items list and the patient detail page's Risk Flags card, both of
 * which surface the same rule-based flags (`src/sephiroth/safety/risk.py`).
 * These are pure string transforms of already-English clinical text, not
 * translation -- i18n for the surrounding label still goes through `t()`. */

const INTERACTION_LABEL_RE = /^Interaction:\s*(.+?)\s*\+\s*(.+)$/i;

/** Alert/risk-flag rows for a drug interaction carry a label like
 * "Interaction: clopidogrel + warfarin" -- pulls the drug pair back out so
 * the caller can re-render it with its own plain phrasing instead of the
 * formal audit-log label. Returns null for any other kind of flag/alert. */
export function parseInteractionLabel(label: string | undefined): { drugA: string; drugB: string } | null {
  const match = label?.match(INTERACTION_LABEL_RE);
  if (!match) return null;
  return { drugA: match[1], drugB: match[2] };
}

const SNOMED_QUALIFIER_RE = /\s*\((disorder|finding|situation|procedure|morphologic abnormality)\)\s*$/i;

/** Synthetic patient data (Synthea) carries SNOMED CT's own qualifier word
 * after each condition name -- "Diabetic renal disease (disorder)", "Body
 * mass index 30+ - obesity (finding)" -- useful for coding, not for a
 * clinician scanning a chart. Display-only; the raw string (used for
 * search/filtering elsewhere) is untouched. */
export function plainCondition(condition: string): string {
  return condition.replace(SNOMED_QUALIFIER_RE, "");
}

/** `sephiroth.clinical.results.classify_lab`'s `classification_reason` is
 * written for an audit trail ("10.5 above the reference range (4.0-5.7).",
 * always English) -- exactly right for a clinician double-checking a
 * threshold, wrong for a patient or a non-clinical reader trying to
 * understand their own result. `plainResultSummary` builds a second,
 * everyday-language sentence from the same underlying numbers instead of
 * re-parsing that string -- same "audit text stays as-is, render a plain
 * one for people" split this file already does for risk flags/conditions
 * above. `classification_reason` is still shown alongside it (smaller,
 * secondary) for anyone who wants the exact threshold. */

const _TEST_KEY_ALIASES: Record<string, string> = {
  k: "potassium",
  "k+": "potassium",
  potasio: "potassium",
  na: "sodium",
  "na+": "sodium",
  sodio: "sodium",
  creatinina: "creatinine",
  glucosa: "glucose",
  glicemia: "glucose",
  a1c: "hba1c",
  hemoglobina: "hemoglobin",
  hb: "hemoglobin",
  plaquetas: "platelets",
  leucocitos: "leukocytes",
  calcio: "calcium",
  magnesio: "magnesium",
  "colesterol ldl": "ldl",
};

function normalizeTestKey(testName: string): string {
  const cleaned = (testName ?? "").toLowerCase().trim();
  return _TEST_KEY_ALIASES[cleaned] ?? cleaned;
}

/** Friendly display name for a lab test key -- falls back to the raw test
 * name (capitalized) when there's no `labs.testName.*` entry for it, so an
 * unmapped test still shows something instead of a raw i18n key string. */
export function friendlyTestName(testName: string | undefined, t: (key: string) => string): string {
  if (!testName) return "";
  const key = `labs.testName.${normalizeTestKey(testName)}`;
  const translated = t(key);
  if (translated !== key) return translated;
  return testName.length > 0 ? testName[0].toUpperCase() + testName.slice(1) : testName;
}

interface PlainResultInput {
  kind: string;
  missing?: boolean;
  test_name?: string;
  value?: number;
  unit?: string;
  reference_low?: number | null;
  reference_high?: number | null;
  modality?: string;
  body_part?: string;
  finding_summary?: string;
}

/** One everyday-language sentence for a lab/imaging result -- "your X was Y,
 * within/outside the normal range" -- instead of the raw
 * `classification_reason` audit string. `severity` is the already-computed
 * classification (`ResultReview.severity`), never re-derived here. */
export function plainResultSummary(
  result: PlainResultInput,
  severity: "critical" | "abnormal" | "normal" | "unclassified",
  t: (key: string) => string,
): string {
  if (result.missing) return t("results.plain.missing");

  if (result.kind === "imaging") {
    return t("results.plain.imaging")
      .replace("{modality}", (result.modality ?? "").toUpperCase())
      .replace("{bodyPart}", result.body_part ?? "")
      .replace("{finding}", result.finding_summary?.trim() || t("results.plain.imagingNoFinding"));
  }

  const test = friendlyTestName(result.test_name, t);
  const unit = result.unit ? ` ${result.unit}` : "";
  const value = result.value ?? "";
  const low = result.reference_low;
  const high = result.reference_high;
  const hasRange = low != null && high != null;

  if (severity === "unclassified") {
    return t("results.plain.unclassified").replace("{test}", test).replace("{value}", `${value}${unit}`);
  }
  if (severity === "critical") {
    return t("results.plain.critical")
      .replace("{test}", test)
      .replace("{value}", `${value}${unit}`);
  }
  if (severity === "abnormal" && hasRange) {
    const direction = (result.value ?? 0) < (low as number) ? "below" : "above";
    return t(`results.plain.abnormal.${direction}`)
      .replace("{test}", test)
      .replace("{value}", `${value}${unit}`)
      .replace("{low}", String(low))
      .replace("{high}", `${high}${unit}`);
  }
  if (severity === "abnormal") {
    return t("results.plain.abnormalNoRange").replace("{test}", test).replace("{value}", `${value}${unit}`);
  }
  // normal
  return hasRange
    ? t("results.plain.normal")
        .replace("{test}", test)
        .replace("{value}", `${value}${unit}`)
        .replace("{low}", String(low))
        .replace("{high}", `${high}${unit}`)
    : t("results.plain.normalNoRange").replace("{test}", test).replace("{value}", `${value}${unit}`);
}
