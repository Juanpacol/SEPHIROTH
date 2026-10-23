"use client";

/** A row of filters read as tabs: the label, a mono count, and a fine line under the one in use that
 * draws itself (the landing's `.nav-underline`). Replaces rows of filled pills; a state's colour appears
 * only in its dot, never as the tab's fill. */
export interface FilterTab<T extends string> {
  value: T;
  label: string;
  count?: number;
  /** Tailwind background class for a small state dot, e.g. `bg-danger`. */
  dot?: string;
}

export default function FilterTabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: FilterTab<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Names the group for assistive technology. */
  label: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0"
    >
      {tabs.map((tab) => {
        const here = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={here}
            data-here={here ? "" : undefined}
            onClick={() => onChange(tab.value)}
            className={`nav-underline tap flex shrink-0 items-center gap-2 px-3.5 py-2 text-sm font-medium transition-colors duration-normal ease-standard ${
              here ? "text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {tab.dot && <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${tab.dot}`} />}
            {tab.label}
            {tab.count !== undefined && (
              <span className="font-mono text-[11px] tabular-nums text-muted">{tab.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
