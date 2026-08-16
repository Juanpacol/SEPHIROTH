"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "@/lib/theme";

const OPTIONS: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

/** iOS-style segmented control for Light/Dark/System, used in Topbar and the profile page. */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useTheme();

  return (
    <div className={`inline-flex items-center gap-0.5 rounded-full bg-primary-soft p-1 ${className}`}>
      {OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          aria-label={label}
          title={label}
          className={`rounded-full p-1.5 transition-colors ${
            theme === value ? "bg-card text-primary shadow-sm" : "text-muted hover:text-primary"
          }`}
        >
          <Icon size={15} />
        </button>
      ))}
    </div>
  );
}
