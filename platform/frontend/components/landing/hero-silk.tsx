"use client";

/** Client-only wrapper around the Silk WebGL background — `next/dynamic`
 * with `ssr: false` because @react-three/fiber's <Canvas> touches `window`
 * at module-eval time and breaks server rendering. Sits absolutely
 * positioned behind the hero copy; `pointer-events-none` keeps the CTA
 * buttons and the interactive walkthrough beneath it clickable. */

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import WebglBoundary from "@/components/effects/webgl-boundary";

const Silk = dynamic(() => import("@/components/effects/silk"), { ssr: false });

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
  } catch {
    return false;
  }
}

export default function HeroSilk() {
  // Feature-detected client-side, not just dynamic-imported: an old GPU,
  // disabled WebGL, or a headless/automated browser can throw *inside*
  // three.js's renderer constructor, which is what WebglBoundary below
  // catches — this check just avoids paying for the mount attempt at all
  // on a browser we already know can't run it.
  const [supported, setSupported] = useState(false);

  useEffect(() => {
    setSupported(hasWebGL());
  }, []);

  if (!supported) return null;

  return (
    <div className="pointer-events-none absolute inset-0 -z-10 opacity-[0.16] dark:opacity-[0.22]" aria-hidden="true">
      <WebglBoundary>
        <Silk color="#646464" speed={3.2} scale={1} noiseIntensity={1.1} rotation={0.15} />
      </WebglBoundary>
    </div>
  );
}
