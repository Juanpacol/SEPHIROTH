"use client";

/** A drawer over a scrim, on one of three edges.
 *
 *   right  — task drawers: booking, working hours, sharing a result.
 *   left   — navigation (the mobile drawer).
 *   bottom — an iOS-style action sheet, and the mobile half of a master-detail
 *            page: render the detail inline under `hidden md:block` and again
 *            inside a `<Sheet side="bottom">` under `md:hidden`. The sheet is
 *            `fixed`, so hiding its wrapper works and neither shape needs a
 *            `useMediaQuery` — same CSS-first trade as `ui/data-list.tsx`.
 *
 * `right` is the default, so the three callers that predate the other two
 * variants pass nothing and behave exactly as before.
 */

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useLanguage } from "@/lib/language";
import Portal from "./portal";
import { useFocusTrap } from "@/lib/hooks/use-focus-trap";

export type SheetSide = "right" | "left" | "bottom";

/** Where the panel sits inside the fixed overlay, and what shape it takes. */
const SIDE: Record<SheetSide, { align: string; panel: string }> = {
  right: { align: "justify-end", panel: "h-full w-full max-w-md border-l" },
  left: { align: "justify-start", panel: "h-full w-full max-w-[19rem] border-r" },
  // `dvh`, not `vh`: Safari's `vh` ignores the collapsible URL bar, so an
  // 85vh sheet hangs off the bottom of the screen on an iPhone.
  bottom: { align: "items-end", panel: "max-h-[85dvh] w-full rounded-t-squircle border-t" },
};

export default function Sheet({
  open,
  onClose,
  title,
  side = "right",
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  side?: SheetSide;
  children: React.ReactNode;
}) {
  const { t } = useLanguage();
  // Callback ref into state, not useRef: the panel does not exist on the render
  // that flips `open`, and a ref object would not re-run the effect when it
  // appears. Setting state does. `ui/dialog.tsx` uses the same pattern.
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

  const { align, panel } = SIDE[side];

  return (
    <Portal>
      <div className={`fixed inset-0 z-50 flex ${align}`} role="dialog" aria-modal="true">
        <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
        <div
          ref={setPanelEl}
          className={`relative flex animate-fadeIn flex-col border-line/60 bg-card shadow-card-lg ${panel}`}
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
          {/* `overscroll-contain` stops a flick past the end of a long sheet
              from scrolling the page behind it on iOS. */}
          <div className="flex-1 overflow-y-auto overscroll-contain p-5">{children}</div>
        </div>
      </div>
    </Portal>
  );
}
