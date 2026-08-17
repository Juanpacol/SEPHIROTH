/** Sample data for the landing page's interactive explanations — kept
 * here, typed, so the walkthrough script and copy stay editable in one
 * place rather than buried in JSX. None of this is live data; it's a
 * fixed script demonstrating how a real consultation flows. */

export interface WalkthroughStage {
  id: string;
  label: string;
  render: "routing" | "specialists" | "synthesize" | "guard" | "verify";
}

export const WALKTHROUGH_STAGES: WalkthroughStage[] = [
  { id: "route", label: "Route", render: "routing" },
  { id: "specialists", label: "Specialists", render: "specialists" },
  { id: "synthesize", label: "Synthesize", render: "synthesize" },
  { id: "guard", label: "Citation Guard", render: "guard" },
  { id: "verify", label: "Verify", render: "verify" },
];

export const SAMPLE_QUESTION = "What A1C goal is appropriate for a 62-year-old with type 2 diabetes?";

export const SAMPLE_SPECIALISTS = [
  { name: "Evidence", finding: "ADA 2024 recommends <7% for most adults, individualized by risk." },
  { name: "Laboratory", finding: "Most recent A1C on file: 8.1% — above target." },
];

export const SAMPLE_DRAFT =
  "Target A1C is <7% [ADA Standards of Care, 2024] [UpToDate Diabetes Review, 2023]. Current value (8.1%) is above goal.";

export const SAMPLE_GUARDED =
  "Target A1C is <7% [ADA Standards of Care, 2024] [unverified — removed]. Current value (8.1%) is above goal.";

export type ClaimState = "supported" | "partial" | "unsupported" | "contradicted" | "unknown";

export interface SampleClaim {
  text: string;
  state: ClaimState;
  evidence: string;
  action: string;
}

export const CLAIM_LEGEND: { state: ClaimState; label: string; color: string }[] = [
  { state: "supported", label: "Supported", color: "text-success" },
  { state: "partial", label: "Partially supported", color: "text-warning" },
  { state: "unsupported", label: "Unsupported", color: "text-danger" },
  { state: "contradicted", label: "Contradicted", color: "text-danger" },
  { state: "unknown", label: "Not enough evidence", color: "text-muted" },
];

export const SAMPLE_CLAIMS: SampleClaim[] = [
  {
    text: "Target A1C is <7% for most adults with type 2 diabetes.",
    state: "supported",
    evidence: '"...an A1C goal of <7% is reasonable for many nonpregnant adults..." — ADA Standards of Care, 2024',
    action: "Kept as-is; citation verified against retrieved evidence.",
  },
  {
    text: "Metformin should be discontinued at this A1C level.",
    state: "contradicted",
    evidence: '"...metformin remains first-line regardless of A1C..." — ADA Standards of Care, 2024',
    action: "Flagged and excluded from the final answer — the abstention gate escalated this claim.",
  },
  {
    text: "A1C should be rechecked in 3 months given the current value.",
    state: "unknown",
    evidence: "No retrieved passage addresses recheck interval for this specific case.",
    action: "Kept, with confidence lowered — no contradiction, but no direct support either.",
  },
];
