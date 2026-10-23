"use client";

import { useRef } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "@/lib/theme";
import { useLanguage } from "@/lib/language";

const OPTIONS: {
  value: Theme;
  icon: typeof Sun;
  labelKey: "common.light" | "common.dark";
}[] = [
  { value: "light", icon: Sun, labelKey: "common.light" },
  { value: "dark", icon: Moon, labelKey: "common.dark" },
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
          {
            duration: 400,
            easing: "ease-in-out",
            pseudoElement: "::view-transition-new(root)",
          }
        );
      })
      .catch(() => {});
  };
}

/** iOS-style segmented control for Light/Dark plus a language toggle, used in Topbar, landing nav, and the profile page. */
export default function ThemeToggle({
  className = "",
  bare = false,
}: {
  className?: string;
  bare?: boolean;
}) {
  const [theme, setTheme] = useTheme();
  const reveal = useThemeRevealTransition();
  const { lang, setLang, t } = useLanguage();

  const resolvesDark = (value: Theme) =>
    value === "dark" || (value === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  const select = (e: React.MouseEvent<HTMLButtonElement>, value: Theme) => {
    if (value === theme) return;
    const appearanceChanges = resolvesDark(value) !== document.documentElement.classList.contains("dark");
    reveal(e.currentTarget, appearanceChanges, () => setTheme(value));
  };

  if (bare) {
    // The top bar's version: no pill, the current theme is the one with a line under it, and the
    // language reads like the landing's switch (mono, wide-tracked).
    return (
      <div className={`inline-flex items-center gap-0.5 ${className}`}>
        {OPTIONS.map(({ value, icon: Icon, labelKey }) => (
          <button
            key={value}
            onClick={(e) => select(e, value)}
            aria-label={t(labelKey)}
            aria-pressed={theme === value}
            title={t(labelKey)}
            data-here={theme === value ? "" : undefined}
            className={`icon-link tap ${theme === value ? "!text-ink" : ""}`}
          >
            <Icon size={16} strokeWidth={1.5} />
          </button>
        ))}
        <button
          onClick={() => setLang(lang === "en" ? "es" : "en")}
          aria-label={t("common.toggleLanguage")}
          title={lang === "en" ? "English" : "Español"}
          className="tap ml-1 inline-flex items-center gap-1.5 rounded-full px-2 font-mono text-[11px] font-semibold tracking-[0.18em]"
        >
          <span className={lang === "en" ? "text-ink" : "text-muted"}>EN</span>
          <span aria-hidden className="text-muted/60">
            /
          </span>
          <span className={lang === "es" ? "text-ink" : "text-muted"}>ES</span>
        </button>
      </div>
    );
  }

  return (
    <div className={`inline-flex items-center gap-0.5 rounded-full bg-primary-soft p-1 ${className}`}>
      {OPTIONS.map(({ value, icon: Icon, labelKey }) => (
        <button
          key={value}
          onClick={(e) => select(e, value)}
          aria-label={t(labelKey)}
          title={t(labelKey)}
          className={`tap flex items-center justify-center rounded-full p-1.5 transition-colors ${
            theme === value ? "bg-card text-primary shadow-hairline" : "text-muted hover:text-primary"
          }`}
        >
          <Icon size={15} />
        </button>
      ))}
      <button
        onClick={() => setLang(lang === "en" ? "es" : "en")}
        aria-label={t("common.toggleLanguage")}
        title={lang === "en" ? "English" : "Español"}
        className="tap rounded-full px-1.5 py-1.5 text-[11px] font-bold text-muted transition-colors hover:text-primary"
      >
        EN/ES
      </button>
    </div>
  );
}
