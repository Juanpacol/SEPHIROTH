/** Sample data for the landing page's interactive explanations — kept
 * here, typed, so the sample claims and copy stay editable in one
 * place rather than buried in JSX. None of this is live data; it's a
 * fixed script demonstrating how a real consultation flows.
 *
 * Text fields hold i18n keys (see `lib/i18n/dictionaries.{en,es}.ts`,
 * `marketing.*` scope), not literal strings — consuming components call
 * `t()` on them, same as everywhere else in the app. */

export type ClaimState = "supported" | "partial" | "unsupported" | "contradicted" | "unknown";

export interface SampleClaim {
  textKey: string;
  state: ClaimState;
  evidenceKey: string;
  actionKey: string;
}

export const CLAIM_LEGEND: { state: ClaimState; labelKey: string; color: string }[] = [
  { state: "supported", labelKey: "marketing.claim.legend.supported", color: "text-success" },
  { state: "partial", labelKey: "marketing.claim.legend.partial", color: "text-warning" },
  { state: "unsupported", labelKey: "marketing.claim.legend.unsupported", color: "text-danger" },
  { state: "contradicted", labelKey: "marketing.claim.legend.contradicted", color: "text-danger" },
  { state: "unknown", labelKey: "marketing.claim.legend.unknown", color: "text-muted" },
];

export const SAMPLE_CLAIMS: SampleClaim[] = [
  {
    textKey: "marketing.claim1.text",
    state: "supported",
    evidenceKey: "marketing.claim1.evidence",
    actionKey: "marketing.claim1.action",
  },
  {
    textKey: "marketing.claim2.text",
    state: "contradicted",
    evidenceKey: "marketing.claim2.evidence",
    actionKey: "marketing.claim2.action",
  },
  {
    textKey: "marketing.claim3.text",
    state: "unknown",
    evidenceKey: "marketing.claim3.evidence",
    actionKey: "marketing.claim3.action",
  },
];
