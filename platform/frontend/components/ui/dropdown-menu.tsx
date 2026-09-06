"use client";

/** The `⋯` row menu — claim, snooze, resolve, dismiss on a task row.
 *
 * Not portalled, unlike `Sheet`/`Dialog`: a dropdown has to stay visually
 * anchored to the button that opened it, and portalling it to `document.body`
 * means reimplementing positioning against scroll and resize for no benefit at
 * this size. The cost is that a dropdown inside a clipping ancestor can be cut
 * off — so on a phone the task row opens a bottom `Sheet` instead of this, which
 * is the better shape for a thumb anyway.
 *
 * No focus trap either, for the same reason it is not portalled: a menu is not
 * modal. It closes on Escape, on outside click, and on choosing an item, and
 * arrow keys move between items. */

import { useCallback, useEffect, useRef, useState } from "react";

export interface MenuItem {
  label: string;
  onSelect: () => void;
  destructive?: boolean;
  disabled?: boolean;
}

export default function DropdownMenu({
  trigger,
  items,
  align = "end",
  label,
}: {
  trigger: React.ReactNode;
  items: MenuItem[];
  align?: "start" | "end";
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const buttons = Array.from(
        listRef.current?.querySelectorAll<HTMLButtonElement>("button:not([disabled])") ?? [],
      );
      if (buttons.length === 0) return;
      e.preventDefault();
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next =
        e.key === "ArrowDown"
          ? buttons[(index + 1) % buttons.length]
          : buttons[(index - 1 + buttons.length) % buttons.length];
      next.focus();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className="tap rounded-full text-muted transition-colors hover:bg-primary-soft hover:text-primary"
      >
        {trigger}
      </button>
      {open && (
        <div
          ref={listRef}
          role="menu"
          className={`absolute z-40 mt-1 min-w-44 overflow-hidden rounded-2xl border border-line/60 bg-card p-1 shadow-card-lg animate-fadeIn ${
            align === "end" ? "right-0" : "left-0"
          }`}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                close();
                item.onSelect();
              }}
              className={`block w-full rounded-xl px-3 py-2 text-left text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                item.destructive
                  ? "text-danger hover:bg-danger/10"
                  : "text-ink/80 hover:bg-primary-soft hover:text-primary"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
