/** How a lab result is put to a patient.
 *
 * The sentence says where the value sits against its range and nothing more: it
 * does not say what the result means for this person. That is the clinician's
 * message, shown next to it. A result with no range, or none the clinician
 * classified, gets "your care team will go over this with you" rather than a
 * judgement this code has no basis for.
 */

import { friendlyTestName } from "@/lib/clinical-text";
import { type PortalLab } from "@/lib/api";

type T = (key: string) => string;

export function labExplanation(lab: PortalLab, t: T): string {
  const test = friendlyTestName(lab.test_name, t);
  const key =
    lab.standing === "inside"
      ? "inside"
      : lab.standing === "outside"
        ? lab.direction
          ? `outside.${lab.direction}`
          : "outside"
        : lab.standing === "needs_attention"
          ? "needs_attention"
          : "unknown";
  return t(`portal.labs.explain.${key}`).replace("{test}", test);
}

/** "3.5–5.1 mmol/L", "≤ 100 mg/dL", or null when no range is known. A
 * non-breaking space keeps the unit from wrapping alone onto a line. */
export function labRange(lab: Pick<PortalLab, "reference_low" | "reference_high" | "unit">): string | null {
  const unit = lab.unit ? `\u00a0${lab.unit}` : "";
  const { reference_low: low, reference_high: high } = lab;
  if (low != null && high != null) return `${low}–${high}${unit}`;
  if (high != null) return `≤ ${high}${unit}`;
  if (low != null) return `≥ ${low}${unit}`;
  return null;
}

export function labValue(lab: Pick<PortalLab, "value" | "unit">): string {
  return `${lab.value}${lab.unit ? `\u00a0${lab.unit}` : ""}`;
}
