"use client";

import { useRef } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "@/lib/theme";
import { useLanguage } from "@/lib/language";

const OPTIONS: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
];

/** Circle-reveal transition, adapted from magicui's `AnimatedThemeToggler`
 * (`components/magicui/animated-theme-toggler.tsx`) — that component is a
 * binary light/dark toggle; this control is tri-state (light/dark/system),
 * so the clip-path math is reused directly here rather than wrapping the
 * vendored component, expanding from whichever segmented-control button
 * was actually clicked. No-ops (falls back to an instant switch) in
 * browsers without the View Transitions API, and does nothing extra when
 * the resolved light/dark appearance doesn't actually change (e.g.
 * light -> system on a light-OS machine) — nothing to animate. */
function useThemeRevealTransition() {
  const isTransitioning = useRef(false);

  return (button: HTMLElement, appearanceChanges: boolean, apply: () => void) => {
    if (typeof document.startViewTransition !== "function" || !appearanceChanges || isTransitioning.current) {
      apply();
      return;
    }

    const { top, left, width, height } = button.getBoundingClientRect();
    const x = left + width / 2;
    const y = top + height / 2;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const maxRadius = Math.hypot(Math.max(x, viewportWidth - x), Math.max(y, viewportHeight - y));
    const toPercent = (px: number, dim: number) => `${(px / dim) * 100}%`;
    const clipFrom = `circle(0% at ${toPercent(x, viewportWidth)} ${toPercent(y, viewportHeight)})`;
    const clipTo = `circle(${(maxRadius / (Math.hypot(viewportWidth, viewportHeight) / Math.SQRT2)) * 100}% at ${toPercent(x, viewportWidth)} ${toPercent(y, viewportHeight)})`;

    isTransitioning.current = true;
    const transition = document.startViewTransition(apply);
    transition.finished.finally(() => {
      isTransitioning.current = false;
    });
    transition.ready
      .then(() => {
        document.documentElement.animate(
          { clipPath: [clipFrom, clipTo] },
          { duration: 400, easing: "ease-in-out", pseudoElement: "::view-transition-new(root)" }
        );
      })
      .catch(() => {});
  };
}

/** iOS-style segmented control for Light/Dark plus a language toggle, used in Topbar, landing nav, and the profile page. */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const reveal = useThemeRevealTransition();
  const { lang, setLang } = useLanguage();

  const resolvesDark = (value: Theme) =>
    value === "dark" || (value === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  const select = (e: React.MouseEvent<HTMLButtonElement>, value: Theme) => {
    if (value === theme) return;
    const appearanceChanges = resolvesDark(value) !== document.documentElement.classList.contains("dark");
    reveal(e.currentTarget, appearanceChanges, () => setTheme(value));
  };

  return (
    <div className={`inline-flex items-center gap-0.5 rounded-full bg-primary-soft p-1 ${className}`}>
      {OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={(e) => select(e, value)}
          aria-label={label}
          title={label}
          className={`rounded-full p-1.5 transition-colors ${
            theme === value ? "bg-card text-primary shadow-sm" : "text-muted hover:text-primary"
          }`}
        >
          <Icon size={15} />
        </button>
      ))}
      <button
        onClick={() => setLang(lang === "en" ? "es" : "en")}
        aria-label="Toggle language"
        title={lang === "en" ? "English" : "Español"}
        className="rounded-full px-1.5 py-1.5 text-[11px] font-bold text-muted transition-colors hover:text-primary"
      >
        EN/ES
      </button>
    </div>
  );
}
