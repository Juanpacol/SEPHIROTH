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
  // `hover:` utilities apply only where the device can hover (`@media (hover: hover)`).
  // On a touch screen a tap leaves the element "hovered" until the next tap, so
  // buttons and cards stay lifted and tinted; this makes that impossible app-wide.
  future: { hoverOnlyWhenSupported: true },
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#3683F8",
          soft: "rgb(var(--color-primary-soft) / <alpha-value>)",
          dark: "#1E62D0",
          // Button fill and text-on-surface shades that clear AA; see globals.css.
          fill: "rgb(var(--color-primary-fill) / <alpha-value>)",
          ink: "rgb(var(--color-primary-ink) / <alpha-value>)",
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
        // Display: tall and condensed, for the landing's big headings only.
        display: ["var(--font-display)", "Impact", "sans-serif"],
        // Labels: small uppercase eyebrows. See `.eyebrow` in globals.css.
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // The type scale. Sizes that were repeated as loose `text-2xl md:text-3xl`
      // or `text-[11px]` are named here; see docs/04-development/design-tokens.md.
      fontSize: {
        // Landing headline: fluid, so it fits 320 px and still reads large on a desk.
        display: ["clamp(2.75rem, 1.6rem + 5.5vw, 5.5rem)", { lineHeight: "1", letterSpacing: "-0.01em" }],
        // Section headings.
        title: ["clamp(1.5rem, 1.2rem + 1.2vw, 2rem)", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        subtitle: ["1.125rem", { lineHeight: "1.5rem" }],
        // 11 px is the floor: below it small caps stop being legible.
        label: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.08em" }],
      },
      spacing: {
        // Height of MobileTabBar (`components/mobile-tab-bar.tsx`). Named so
        // the pages that must clear it don't hardcode the same 4rem twice.
        tabbar: "4rem",
      },
      // Apple HIG's minimum comfortable touch target (44pt). Backs the `.tap`
      // utility in globals.css — see its comment for why it's size-only.
      minHeight: { tap: "44px" },
      minWidth: { tap: "44px" },
      borderRadius: {
        // iOS-style "continuous corner" scale — larger than Tailwind's defaults.
        xl2: "1.25rem",
        squircle: "1.75rem",
        // Nested radii: a surface, the controls on it, and what sits inside a card.
        // An inner corner is its container's radius minus the padding between them.
        card: "1.75rem",
        control: "1rem",
        inner: "0.75rem",
      },
      // Every surface starts with the same hairline (a 1px ring in `line`, drawn as a
      // shadow so it adds no size) and stacks short shadows on it: tight, so a card
      // reads as a thin layer on the page, not as a cloud around it.
      boxShadow: {
        hairline: "0 0 0 1px rgb(var(--color-line) / 0.6)",
        // Not `card`: Tailwind also makes `shadow-<colour>` utilities, and the theme has a
        // colour called `card`; its rule (shadow-card: white in light, navy in dark) beat
        // this shadow, so cards had a halo in their own colour instead of a shadow.
        raised: "0 0 0 1px rgb(var(--color-line) / 0.6), 0 1px 2px rgb(var(--shadow-ink) / calc(0.06 * var(--shadow-strength))), 0 4px 10px -2px rgb(var(--shadow-ink) / calc(0.08 * var(--shadow-strength)))",
        "raised-lg":
          "0 0 0 1px rgb(var(--color-line) / 0.8), 0 2px 4px rgb(var(--shadow-ink) / calc(0.08 * var(--shadow-strength))), 0 10px 24px -6px rgb(var(--shadow-ink) / calc(0.18 * var(--shadow-strength)))",
        popover:
          "0 0 0 1px rgb(var(--color-line) / 0.8), 0 4px 8px rgb(var(--shadow-ink) / calc(0.1 * var(--shadow-strength))), 0 20px 40px -8px rgb(var(--shadow-ink) / calc(0.25 * var(--shadow-strength)))",
        button: "0 1px 2px rgb(var(--shadow-ink) / calc(0.18 * var(--shadow-strength)))",
        "button-lift": "0 2px 4px rgb(var(--shadow-ink) / calc(0.2 * var(--shadow-strength))), 0 6px 12px -2px rgb(var(--shadow-ink) / calc(0.2 * var(--shadow-strength)))",
      },
      // Motion tokens (values live in globals.css `:root`).
      transitionDuration: {
        fast: "var(--duration-fast)",
        normal: "var(--duration-normal)",
        slow: "var(--duration-slow)",
      },
      transitionTimingFunction: {
        // UIKit's default spring-ish curve: a slight overshoot then settle.
        ios: "cubic-bezier(0.34, 1.56, 0.64, 1)",
        standard: "var(--ease-standard)",
        emphasized: "var(--ease-emphasized)",
        sheet: "var(--ease-sheet)",
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
        // Entrances travel a few pixels and fade; they never slide in from off screen.
        toastIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        toastOut: { to: { opacity: "0", transform: "translateY(4px)" } },
        scrimIn: { from: { opacity: "0" } },
        scrimOut: { to: { opacity: "0" } },
        sheetInRight: { from: { opacity: "0", transform: "translateX(24px)" } },
        sheetOutRight: { to: { opacity: "0", transform: "translateX(24px)" } },
        sheetInLeft: { from: { opacity: "0", transform: "translateX(-24px)" } },
        sheetOutLeft: { to: { opacity: "0", transform: "translateX(-24px)" } },
        sheetInBottom: { from: { opacity: "0", transform: "translateY(24px)" } },
        sheetOutBottom: { to: { opacity: "0", transform: "translateY(24px)" } },
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
        // Enter at the slow duration and leave faster: leaving should not make anyone wait.
        "toast-in": "toastIn var(--duration-normal) var(--ease-emphasized) both",
        "toast-out": "toastOut var(--duration-fast) var(--ease-standard) both",
        "scrim-in": "scrimIn var(--duration-slow) var(--ease-standard) both",
        "scrim-out": "scrimOut var(--duration-normal) var(--ease-standard) both",
        "sheet-in-right": "sheetInRight var(--duration-slow) var(--ease-sheet) both",
        "sheet-out-right": "sheetOutRight var(--duration-normal) var(--ease-standard) both",
        "sheet-in-left": "sheetInLeft var(--duration-slow) var(--ease-sheet) both",
        "sheet-out-left": "sheetOutLeft var(--duration-normal) var(--ease-standard) both",
        "sheet-in-bottom": "sheetInBottom var(--duration-slow) var(--ease-sheet) both",
        "sheet-out-bottom": "sheetOutBottom var(--duration-normal) var(--ease-standard) both",
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
