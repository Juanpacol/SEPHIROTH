import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";
export const runtime = "edge";

// Deliberately no custom font — next/og's ImageResponse would need to
// fetch one at build time, which has no network guarantee in CI. This
// image has no text anyway, only the wing mark.
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0B1220",
          borderRadius: 40,
        }}
      >
        <svg
          width="110"
          height="110"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#7FB0FF"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 20 Q9 7 21 4" />
          <path d="M6.5 21 Q13 16 21 9.5" />
          <path d="M6 19.4 Q7.6 18.2 8.6 16.4" />
          <path d="M8.2 17.6 Q10 16.6 11.2 14.6" />
          <path d="M10.6 15.6 Q12.1 14.8 13 13.1" />
          <path d="M13 13.4 Q14.2 12.8 15 11.4" />
        </svg>
      </div>
    ),
    { ...size }
  );
}
