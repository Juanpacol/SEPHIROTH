/** "How it works" as an answer taken apart: one sample answer, and the five things that happened
 * to it before the reader saw it, each pinned to the part of the answer it is about. The copy is in
 * the dictionaries (`marketing.anatomy.*`); this file says which part each step points at.
 *
 * Every step is something the product does today: routing (`runtime/intent_router.py`), the
 * specialist writing from retrieved evidence, the citation guard (`verification/citation_guard.py`),
 * the claim check (`verification/`), and the abstention gate (`safety/abstention.py`). */
export type AnatomyStepId = "route" | "write" | "guard" | "verify" | "abstain";

export interface AnatomyStep {
  id: AnatomyStepId;
  titleKey: string;
  bodyKey: string;
}

export const ANATOMY_STEPS: AnatomyStep[] = (["route", "write", "guard", "verify", "abstain"] as const).map(
  (id) => ({
    id,
    titleKey: `marketing.anatomy.step.${id}.title`,
    bodyKey: `marketing.anatomy.step.${id}.body`,
  }),
);
