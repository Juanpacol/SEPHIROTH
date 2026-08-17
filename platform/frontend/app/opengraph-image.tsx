import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const runtime = "edge";

// No custom font — the system stack keeps this hermetic (no network
// fetch at build time), same reasoning as apple-icon.tsx.
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#0B1220",
          color: "#F5F5F7",
          fontFamily: "sans-serif",
        }}
      >
        <svg
          width="90"
          height="90"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#7FB0FF"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ marginBottom: 28 }}
        >
          <path d="M4 20 Q9 7 21 4" />
          <path d="M6.5 21 Q13 16 21 9.5" />
          <path d="M6 19.4 Q7.6 18.2 8.6 16.4" />
          <path d="M8.2 17.6 Q10 16.6 11.2 14.6" />
          <path d="M10.6 15.6 Q12.1 14.8 13 13.1" />
          <path d="M13 13.4 Q14.2 12.8 15 11.4" />
        </svg>
        <div style={{ display: "flex", fontSize: 64, fontWeight: 800, letterSpacing: -1 }}>
          SEPHIROTH
        </div>
        <div style={{ display: "flex", fontSize: 28, color: "#98989D", marginTop: 12 }}>
          Clinical decisions, with the reasoning shown
        </div>
      </div>
    ),
    { ...size }
  );
}
