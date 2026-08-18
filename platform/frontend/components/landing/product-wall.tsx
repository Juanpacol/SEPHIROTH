"use client";

/** Drifting wall of real product screenshots (dashboard, patients, evidence
 * search, imaging vision streaming, copilot, agents activity) — not stock
 * photos. `next/dynamic` + `ssr: false` because DriftWall reads
 * `window.matchMedia` and uses `ResizeObserver` at mount. */

import dynamic from "next/dynamic";

const DriftWall = dynamic(() => import("@/components/effects/drift-wall"), { ssr: false });

const SCREENSHOTS = [
  { image: "/landing/dashboard.jpg", title: "Dashboard overview" },
  { image: "/landing/copilot-working.jpg", title: "Copilot Chat, mid-consultation" },
  { image: "/landing/evidence-results.jpg", title: "Evidence Library, cited results" },
  { image: "/landing/imaging-vision.jpg", title: "Imaging Analysis, live vision description" },
  { image: "/landing/patients.jpg", title: "Patient list with risk flags" },
  { image: "/landing/agents.jpg", title: "Agents Activity" },
];

export default function ProductWall() {
  return (
    <div className="h-[420px] w-full overflow-hidden rounded-squircle border border-line/60 bg-ink md:h-[520px]">
      <DriftWall
        items={SCREENSHOTS}
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
