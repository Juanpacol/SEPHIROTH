/** The landing page's feature showcase: what SEPHIROTH does, one step at a time, each
 * with a media panel beside it. Every claim here is something the product does today;
 * see the code each one names.
 *
 * To put a picture or a video in a panel, add the file under `public/landing/features/`
 * and fill in that feature's `media` below (see the README in that folder). A feature
 * with no media shows a designed tile (its number and verb), so the page is finished
 * either way. */
export type FeatureMedia =
  | { kind: "placeholder" }
  | { kind: "image"; src: string; altKey: string }
  /** A short, silent loop. `poster` is what shows before it loads, and the whole time under
   * reduced motion. Keep it under 3 MB; mp4 (H.264) for Safari plus webm if you can. */
  | { kind: "video"; src: string; poster: string; altKey: string; webm?: string };

export interface LandingFeature {
  id: string;
  verbKey: string;
  titleKey: string;
  bodyKey: string;
  media: FeatureMedia;
}

export const LANDING_FEATURES: LandingFeature[] = [
  {
    // `runtime/intent_router.py`: every question goes to exactly one specialist.
    id: "ask",
    verbKey: "marketing.features.ask.verb",
    titleKey: "marketing.features.ask.title",
    bodyKey: "marketing.features.ask.body",
    media: { kind: "placeholder" },
  },
  {
    // `verification/citation_guard.py` and the evidence agent: guidelines and PubMed only.
    id: "cite",
    verbKey: "marketing.features.cite.verb",
    titleKey: "marketing.features.cite.title",
    bodyKey: "marketing.features.cite.body",
    media: { kind: "placeholder" },
  },
  {
    // `verification/` (five claim states) and `safety/abstention.py`.
    id: "verify",
    verbKey: "marketing.features.verify.verb",
    titleKey: "marketing.features.verify.title",
    bodyKey: "marketing.features.verify.body",
    media: { kind: "placeholder" },
  },
  {
    // `intelligence/mcp/vision_server.py`: a description of what is visible, not a diagnosis.
    id: "see",
    verbKey: "marketing.features.see.verb",
    titleKey: "marketing.features.see.title",
    bodyKey: "marketing.features.see.body",
    media: { kind: "image", src: "/landing/analysis/xray.webp", altKey: "marketing.features.see.alt" },
  },
  {
    // `clinical/results.py` and the results inbox: reference ranges, critical values, review.
    id: "follow",
    verbKey: "marketing.features.follow.verb",
    titleKey: "marketing.features.follow.title",
    bodyKey: "marketing.features.follow.body",
    media: { kind: "placeholder" },
  },
  {
    // `api/patient_labs.py`: a patient sees a result only after a clinician has communicated it.
    id: "share",
    verbKey: "marketing.features.share.verb",
    titleKey: "marketing.features.share.title",
    bodyKey: "marketing.features.share.body",
    media: { kind: "placeholder" },
  },
];
