"use client";

/** Which patient the question is about, as a small pill that opens a list upward. A native `<select>` was
 * replaced because its popup is drawn by the operating system, in its own grey, and cannot take the
 * assistant's palette. Opens on click; closes on Escape (focus returns to the pill), on a click outside, and
 * when a patient is chosen. A disclosure with a listbox, with the arrow keys moving between options. */

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronUp, User } from "lucide-react";

export interface PickerPatient {
  id: string;
  name: string;
}

export default function PatientPicker({
  patients,
  value,
  onChange,
  noneLabel,
  placement = "up",
}: {
  patients: PickerPatient[];
  value: string;
  onChange: (id: string) => void;
  noneLabel: string;
  /** Which way the list opens: `up` in the chat's composer, `down` in a page's filter row. */
  placement?: "up" | "down";
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const options = [{ id: "", name: noneLabel }, ...patients];
  const current = options.find((o) => o.id === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" && open) {
      e.stopPropagation();
      close(true);
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    if (!open) {
      setOpen(true);
      return;
    }
    const items = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? Math.min(items.length - 1, at + 1) : Math.max(0, at - 1);
    items[next]?.focus();
  };

  return (
    <div ref={rootRef} className="relative min-w-0" onKeyDown={onKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        className="tap flex max-w-full items-center gap-1.5 rounded-full border border-line/70 px-3 py-1.5 text-xs font-medium text-ink/90 transition-colors duration-normal hover:border-primary-ink/60 hover:bg-primary-soft/30"
      >
        <User size={13} strokeWidth={1.5} className="shrink-0 text-primary-ink" aria-hidden />
        <span className="min-w-0 truncate">{current.name}</span>
        <ChevronUp
          size={13}
          strokeWidth={1.5}
          aria-hidden
          className={`shrink-0 text-muted transition-transform duration-normal ${open ? "" : "rotate-180"}`}
        />
      </button>
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-activedescendant={undefined}
          className={`absolute left-0 z-10 max-h-56 min-w-[12rem] max-w-[min(20rem,80vw)] animate-fadeIn overflow-y-auto rounded-2xl border border-line/60 bg-card p-1.5 shadow-raised-lg ${placement === "up" ? "bottom-full mb-2" : "top-full mt-2"}`}
        >
          {options.map((o) => {
            const selected = o.id === value;
            return (
              <li
                key={o.id || "none"}
                role="option"
                aria-selected={selected}
                tabIndex={0}
                onClick={() => {
                  onChange(o.id);
                  close(true);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onChange(o.id);
                    close(true);
                  }
                }}
                className={`tap flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2 text-sm transition-colors duration-normal hover:bg-primary-soft/50 focus-visible:!outline-none focus-visible:bg-primary-soft/50 ${
                  selected ? "text-primary-ink" : "text-ink/90"
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{o.name}</span>
                {selected && <Check size={14} strokeWidth={1.75} aria-hidden className="shrink-0" />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
