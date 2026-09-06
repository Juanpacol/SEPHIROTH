"use client";

/** Glassmorphism hover-card gallery — one real sample per imaging modality
 * the vision pipeline supports (`SUPPORTED_MODALITIES` in
 * intelligence/mcp/imaging_server.py). All five images are CC0/public-domain
 * (Wikimedia Commons) — never the RSNA samples in real_data/, which are
 * academic/non-commercial and explicitly not redistributable. Card styling
 * adapted from a public-domain CSS pattern (backdrop-filter blur+saturate,
 * translateY lift on hover); backdrop uses primary/ink tokens, not the
 * sephiroth gradient reserved for AI-generated content (CLAUDE.md #4). */

import { useLanguage } from "@/lib/language";

const ITEMS = [
  { image: "/landing/analysis/xray.webp", titleKey: "marketing.analysisGallery.xray.title", captionKey: "marketing.analysisGallery.xray.caption" },
  { image: "/landing/analysis/ct-brain.webp", titleKey: "marketing.analysisGallery.ct.title", captionKey: "marketing.analysisGallery.ct.caption" },
  { image: "/landing/analysis/mri-brain.webp", titleKey: "marketing.analysisGallery.mri.title", captionKey: "marketing.analysisGallery.mri.caption" },
  { image: "/landing/analysis/ultrasound.webp", titleKey: "marketing.analysisGallery.ultrasound.title", captionKey: "marketing.analysisGallery.ultrasound.caption" },
  { image: "/landing/analysis/pathology.webp", titleKey: "marketing.analysisGallery.pathology.title", captionKey: "marketing.analysisGallery.pathology.caption" },
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
  return (
    <div
      className="grid grid-cols-2 gap-5 rounded-squircle border border-line/60 p-6 sm:grid-cols-3 md:grid-cols-5 md:p-10"
      style={BACKDROP}
    >
      {ITEMS.map((item) => (
        <article
          key={item.image}
          className="group relative rounded-2xl border border-white/25 bg-white/10 p-3 shadow-[0_24px_50px_-26px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.4)] backdrop-blur-md backdrop-saturate-150 transition-all duration-300 hover:-translate-y-2 hover:border-white/45 hover:shadow-[0_36px_64px_-26px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.55)]"
        >
          <span className="pointer-events-none absolute inset-x-[14%] top-0 h-px bg-gradient-to-r from-transparent via-white/80 to-transparent" />
          <div className="overflow-hidden rounded-xl border border-white/20 bg-white/10">
            {/* eslint-disable-next-line @next/next/no-img-element -- these are
                five static local webp thumbnails already lazy-loaded at a fixed
                aspect ratio. Moving to next/image means `fill` plus a relative
                parent, a layout change on a page nobody can visually verify in
                CI; it belongs with the landing rewrite, not here. */}
            <img
              src={item.image}
              alt={t(item.titleKey)}
              loading="lazy"
              decoding="async"
              className="aspect-[4/3] w-full object-cover"
            />
          </div>
          <h3 className="mt-3 text-sm font-bold text-white [text-shadow:0_1px_6px_rgba(0,0,0,0.25)]">
            {t(item.titleKey)}
          </h3>
          <p className="mt-0.5 text-xs text-white/80">{t(item.captionKey)}</p>
        </article>
      ))}
    </div>
  );
}
