import type { Config } from "tailwindcss";

/**
 * Design tokens derived from the Nexura Care healthcare dashboard reference
 * (Behance, Mohammed Agami) + the project's Sephiroth/Platino metallic accent.
 * Reuse these tokens — do not invent new colors.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#3683F8",
          soft: "#EAF2FE",
          dark: "#1E62D0",
        },
        ink: "#060606",
        surface: "#EBF3FE",
        card: "#FFFFFF",
        line: "#D8D8D8",
        muted: "#8A94A6",
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
      boxShadow: {
        card: "0 1px 3px rgba(16, 42, 83, 0.06), 0 8px 24px rgba(16, 42, 83, 0.06)",
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
      },
      animation: {
        fadeIn: "fadeIn 0.3s ease-out",
        thinkingDot: "thinkingDot 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
