import type { Config } from "tailwindcss";

/**
 * Design tokens derived from the Nexura Care healthcare dashboard reference
 * (Behance, Mohammed Agami) + the project's Sephiroth/Platino metallic accent,
 * restyled toward Apple's Human Interface Guidelines (large radii, translucency,
 * light/dark parity). Reuse these tokens — do not invent new colors.
 *
 * `ink`/`surface`/`card`/`line`/`muted`/`primary.soft` are backed by CSS custom
 * properties (see app/globals.css `:root`/`.dark`) so they flip with the theme;
 * `primary`/`primary.dark`, the status colors, and the Sephiroth gradient stay
 * identical in both themes — the Sephiroth gradient in particular is the fixed
 * "AI-generated content" signal (CLAUDE.md decision #4) and must not vary.
 */
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#3683F8",
          soft: "rgb(var(--color-primary-soft) / <alpha-value>)",
          dark: "#1E62D0",
        },
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        card: "rgb(var(--color-card) / <alpha-value>)",
        line: "rgb(var(--color-line) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444",
        sephiroth: {
          start: "#8C92AC",
          end: "#D1D5DB",
        },
      },
      fontFamily: {
        sans: ["var(--font-manrope)", "sans-serif"],
      },
      borderRadius: {
        // iOS-style "continuous corner" scale — larger than Tailwind's defaults.
        xl2: "1.25rem",
        squircle: "1.75rem",
      },
      boxShadow: {
        card: "0 1px 3px rgba(16, 42, 83, 0.06), 0 8px 24px rgba(16, 42, 83, 0.06)",
        "card-lg": "0 4px 10px rgba(16, 42, 83, 0.08), 0 16px 40px rgba(16, 42, 83, 0.12)",
      },
      transitionTimingFunction: {
        // UIKit's default spring-ish curve: a slight overshoot then settle.
        ios: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      backgroundImage: {
        // Metallic pauldron gradient — marks AI-generated content.
        sephiroth: "linear-gradient(135deg, #8C92AC 0%, #D1D5DB 100%)",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(-4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        thinkingDot: {
          "0%, 60%, 100%": { opacity: "0.25", transform: "translateY(0)" },
          "30%": { opacity: "1", transform: "translateY(-1.5px)" },
        },
        // magicui Marquee — ported from its v4 `@theme inline` block since
        // this project is on Tailwind v3 (no `@theme`, config-based instead).
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(calc(-100% - var(--gap)))" },
        },
        "marquee-vertical": {
          from: { transform: "translateY(0)" },
          to: { transform: "translateY(calc(-100% - var(--gap)))" },
        },
        // magicui ShimmerButton
        "shimmer-slide": {
          to: { transform: "translate(calc(100cqw - 100%), 0)" },
        },
        "spin-around": {
          "0%": { transform: "translateZ(0) rotate(0)" },
          "15%, 35%": { transform: "translateZ(0) rotate(90deg)" },
          "65%, 85%": { transform: "translateZ(0) rotate(270deg)" },
          "100%": { transform: "translateZ(0) rotate(360deg)" },
        },
      },
      animation: {
        fadeIn: "fadeIn 0.3s ease-out",
        thinkingDot: "thinkingDot 1.2s ease-in-out infinite",
        marquee: "marquee var(--duration, 40s) infinite linear",
        "marquee-vertical": "marquee-vertical var(--duration, 40s) linear infinite",
        "shimmer-slide": "shimmer-slide var(--speed, 3s) ease-in-out infinite alternate",
        "spin-around": "spin-around calc(var(--speed, 3s) * 2) infinite linear",
      },
    },
  },
  plugins: [],
};

export default config;
