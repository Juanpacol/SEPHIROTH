"use client";

/** A drawer over a scrim — used for booking, editing working hours, and
 * sharing a result, and from here on for mobile navigation and task actions.
 *
 * It renders through `Portal` and traps focus with `useFocusTrap`. Both were
 * missing until the mobile shell needed a drawer: an overlay left in normal DOM
 * order is clipped by any `overflow:hidden`/`backdrop-blur` ancestor (this app
 * has several), and one without a focus trap is modal only to people using a
 * mouse.
 *
 * `side` defaults to `right`, which is what every existing caller gets without
 * changing a line. `bottom` is the phone shape: a sheet that rises from the
 * bottom edge, within thumb reach, instead of a full-height panel. */

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useLanguage } from "@/lib/language";
import { useFocusTrap } from "@/lib/hooks/use-focus-trap";
import Portal from "./portal";

export default function Sheet({
  open,
  onClose,
  title,
  children,
  side = "right",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  side?: "right" | "bottom";
}) {
  const { t } = useLanguage();
  // A callback ref into state, not `useRef`: `Portal` mounts its children one
  // render after this one, so a ref's `.current` would still be null when the
  // trap's effect first runs and nothing would re-trigger it.
  const [panelEl, setPanelEl] = useState<HTMLDivElement | null>(null);
  useFocusTrap(panelEl, open);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const panel =
    side === "bottom"
      ? "mt-auto max-h-[85vh] w-full rounded-t-squircle border-t"
      : "ml-auto h-full w-full max-w-md border-l";

  return (
    <Portal>
      <div
        className={`fixed inset-0 z-50 flex ${side === "bottom" ? "flex-col" : "justify-end"}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
        <div
          ref={setPanelEl}
          className={`glass-surface relative flex flex-col border-line/60 shadow-card animate-fadeIn ${panel}`}
        >
          <div className="flex items-center justify-between border-b border-line/60 px-5 py-4">
            <h2 className="text-base font-bold">{title}</h2>
            <button
              onClick={onClose}
              aria-label={t("common.close")}
              className="tap rounded-full p-1.5 text-muted hover:bg-primary-soft"
            >
              <X size={18} />
            </button>
          </div>
          <div className="safe-bottom flex-1 overflow-y-auto p-5">{children}</div>
        </div>
      </div>
    </Portal>
  );
}
