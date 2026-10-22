import type { ClaimState } from "@/lib/landing-content";

/** The example answers the landing hero cycles through. They are written for the page,
 * not read from a model: the public page never calls one. Each shows something the
 * product does (a cited guideline answer, a drug interaction, and a refusal to guess),
 * and none states a clinical fact that is not common knowledge or that a source named
 * here does not back. The page labels them as examples. */
export interface AnswerExample {
  id: "guideline" | "drug" | "decline";
  tabKey: string;
  questionKey: string;
  /** Which of the three agents answers (`marketing.agentName.*`). */
  agentKey: string;
  answerKey: string;
  /** Source names are proper nouns and stay as they are in every language. */
  citations: string[];
  claims: { textKey: string; state: ClaimState }[];
  outcome: "answer" | "decline";
  outcomeKey: string;
}

export const ANSWER_EXAMPLES: AnswerExample[] = [
  {
    id: "guideline",
    tabKey: "marketing.answer.guideline.tab",
    questionKey: "marketing.answer.guideline.question",
    agentKey: "marketing.agentName.evidence",
    answerKey: "marketing.answer.guideline.answer",
    citations: ["ADA Standards of Care, 2024"],
    claims: [
      { textKey: "marketing.answer.guideline.claim1", state: "supported" },
      { textKey: "marketing.answer.guideline.claim2", state: "supported" },
    ],
    outcome: "answer",
    outcomeKey: "marketing.answer.guideline.outcome",
  },
  {
    id: "drug",
    tabKey: "marketing.answer.drug.tab",
    questionKey: "marketing.answer.drug.question",
    agentKey: "marketing.agentName.drugSafety",
    answerKey: "marketing.answer.drug.answer",
    citations: ["DDInter"],
    claims: [
      { textKey: "marketing.answer.drug.claim1", state: "supported" },
      { textKey: "marketing.answer.drug.claim2", state: "supported" },
    ],
    outcome: "answer",
    outcomeKey: "marketing.answer.drug.outcome",
  },
  {
    id: "decline",
    tabKey: "marketing.answer.decline.tab",
    questionKey: "marketing.answer.decline.question",
    agentKey: "marketing.agentName.evidence",
    answerKey: "marketing.answer.decline.answer",
    citations: [],
    claims: [{ textKey: "marketing.answer.decline.claim1", state: "unknown" }],
    outcome: "decline",
    outcomeKey: "marketing.answer.decline.outcome",
  },
];
