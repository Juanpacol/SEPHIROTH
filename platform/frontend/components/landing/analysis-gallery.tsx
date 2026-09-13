"use client";

/** Animated masonry gallery — two real samples per imaging modality the
 * vision pipeline supports (`SUPPORTED_MODALITIES` in
 * intelligence/mcp/imaging_server.py). All ten images are CC0/public-domain
 * (Wikimedia Commons) — never the RSNA samples in real_data/, which are
 * academic/non-commercial and explicitly not redistributable. Layout is
 * reactbits.dev's Masonry component (see components/landing/masonry.tsx),
 * replacing the earlier glassmorphism CSS-grid gallery. Backdrop uses
 * primary/ink tokens, not the sephiroth gradient reserved for
 * AI-generated content (CLAUDE.md #4). */

import { useCallback, useMemo, useState } from "react";
import { useLanguage } from "@/lib/language";
import Masonry, { type MasonryItem } from "./masonry";

const ITEMS = [
  { id: "xray", image: "/landing/analysis/xray.webp", titleKey: "marketing.analysisGallery.xray.title", captionKey: "marketing.analysisGallery.xray.caption", height: 420 },
  { id: "ct", image: "/landing/analysis/ct-brain.webp", titleKey: "marketing.analysisGallery.ct.title", captionKey: "marketing.analysisGallery.ct.caption", height: 560 },
  { id: "mri", image: "/landing/analysis/mri-brain.webp", titleKey: "marketing.analysisGallery.mri.title", captionKey: "marketing.analysisGallery.mri.caption", height: 480 },
  { id: "ultrasound", image: "/landing/analysis/ultrasound.webp", titleKey: "marketing.analysisGallery.ultrasound.title", captionKey: "marketing.analysisGallery.ultrasound.caption", height: 600 },
  { id: "pathology", image: "/landing/analysis/pathology.webp", titleKey: "marketing.analysisGallery.pathology.title", captionKey: "marketing.analysisGallery.pathology.caption", height: 440 },
  { id: "xray2", image: "/landing/analysis/xray-2.webp", titleKey: "marketing.analysisGallery.xray2.title", captionKey: "marketing.analysisGallery.xray2.caption", height: 540 },
  { id: "ct2", image: "/landing/analysis/ct-abdomen.webp", titleKey: "marketing.analysisGallery.ct2.title", captionKey: "marketing.analysisGallery.ct2.caption", height: 460 },
  { id: "mri2", image: "/landing/analysis/mri-spine.webp", titleKey: "marketing.analysisGallery.mri2.title", captionKey: "marketing.analysisGallery.mri2.caption", height: 620 },
  { id: "ultrasound2", image: "/landing/analysis/ultrasound-2.webp", titleKey: "marketing.analysisGallery.ultrasound2.title", captionKey: "marketing.analysisGallery.ultrasound2.caption", height: 400 },
  { id: "pathology2", image: "/landing/analysis/pathology-2.webp", titleKey: "marketing.analysisGallery.pathology2.title", captionKey: "marketing.analysisGallery.pathology2.caption", height: 500 },
];

const BACKDROP = {
  backgroundImage: [
    "radial-gradient(45% 65% at 15% 20%, rgba(54,131,248,0.55), transparent 60%)",
    "radial-gradient(45% 65% at 85% 15%, rgba(30,98,208,0.5), transparent 60%)",
    "radial-gradient(60% 70% at 50% 100%, rgba(54,131,248,0.35), transparent 60%)",
    "linear-gradient(135deg, #0B1220, #142036)",
  ].join(", "),
};

export default function AnalysisGallery() {
  const { t } = useLanguage();
  const [contentHeight, setContentHeight] = useState(640);

  const items: MasonryItem[] = useMemo(
    () =>
      ITEMS.map((item) => ({
        id: item.id,
        img: item.image,
        height: item.height,
        title: t(item.titleKey),
        caption: t(item.captionKey),
      })),
    [t]
  );

  const handleLayout = useCallback((height: number) => {
    setContentHeight(Math.max(height, 320));
  }, []);

  return (
    <div className="rounded-squircle border border-line/60 p-6 md:p-10" style={BACKDROP}>
      <div style={{ position: "relative", height: contentHeight, transition: "height 0.3s ease" }}>
        <Masonry
          items={items}
          animateFrom="bottom"
          blurToFocus
          scaleOnHover
          hoverScale={0.96}
          duration={0.5}
          stagger={0.08}
          onLayout={handleLayout}
        />
      </div>
    </div>
  );
}
