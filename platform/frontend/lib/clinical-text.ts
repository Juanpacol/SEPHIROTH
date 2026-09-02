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
