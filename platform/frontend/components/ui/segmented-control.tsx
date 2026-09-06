"use client";

/** iOS-style segmented control — "Mías / Sin asignar / Todas" on the task
 * inbox, and the tab strip on the patient page once it has to survive a
 * 375px screen.
 *
 * Scrollable rather than wrapping: three segments fit a phone, six do not, and
 * a control that reflows to two rows stops reading as one control. Arrow keys
 * move between options, which is what the `tablist` role promises. */

export interface Segment<T extends string> {
  value: T;
  label: string;
  /** Rendered as a trailing count pill — an inbox filter is much more useful
   * when you can see there is nothing behind it before switching. */
  count?: number;
}

export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Segment<T>[];
  value: T;
  onChange: (next: T) => void;
  label: string;
}) {
  const move = (delta: number) => {
    const index = options.findIndex((o) => o.value === value);
    if (index === -1) return;
    const next = options[(index + delta + options.length) % options.length];
    onChange(next.value);
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="flex gap-1 overflow-x-auto rounded-2xl bg-primary-soft/60 p-1"
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") {
          e.preventDefault();
          move(1);
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          move(-1);
        }
      }}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(option.value)}
            className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-semibold transition-all duration-200 ease-ios ${
              active ? "bg-card text-primary shadow-sm" : "text-ink/60 hover:text-primary"
            }`}
          >
            {option.label}
            {option.count !== undefined && (
              <span
                className={`rounded-full px-1.5 text-[11px] font-bold ${
                  active ? "bg-primary-soft text-primary" : "bg-card/70 text-muted"
                }`}
              >
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
