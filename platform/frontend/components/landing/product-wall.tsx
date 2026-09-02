"use client";

/** Drifting wall of real product screenshots (dashboard, patients, evidence
 * search, imaging vision streaming, copilot, agents activity) — not stock
 * photos. `next/dynamic` + `ssr: false` because DriftWall reads
 * `window.matchMedia` and uses `ResizeObserver` at mount. */

import dynamic from "next/dynamic";
import { useLanguage } from "@/lib/language";

const DriftWall = dynamic(() => import("@/components/effects/drift-wall"), { ssr: false });

const SCREENSHOTS = [
  { image: "/landing/dashboard.jpg", titleKey: "marketing.productWall.screenshot.dashboard" },
  { image: "/landing/copilot-working.jpg", titleKey: "marketing.productWall.screenshot.copilot" },
  { image: "/landing/evidence-results.jpg", titleKey: "marketing.productWall.screenshot.evidence" },
  { image: "/landing/imaging-vision.jpg", titleKey: "marketing.productWall.screenshot.imaging" },
  { image: "/landing/patients.jpg", titleKey: "marketing.productWall.screenshot.patients" },
  { image: "/landing/agents.jpg", titleKey: "marketing.productWall.screenshot.agents" },
];

export default function ProductWall() {
  const { t } = useLanguage();
  const screenshots = SCREENSHOTS.map((s) => ({ image: s.image, title: t(s.titleKey) }));
  return (
    <div className="h-[420px] w-full overflow-hidden rounded-squircle border border-line/60 bg-ink md:h-[520px]">
      <DriftWall
        items={screenshots}
        columns={5}
        tileWidth={190}
        tileHeight={126}
        speed={26}
        variance={0.4}
        parallax={0.5}
        dim={0.5}
        fade={0.62}
        overlayColor="#14181F"
      />
    </div>
  );
}
