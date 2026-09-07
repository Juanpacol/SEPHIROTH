"use client";

/** A centred modal for a decision that needs a reason or a confirmation —
 * dismissing a clinical task, cancelling an appointment.
 *
 * `Sheet` is the drawer for *doing* something with room to work; this is the
 * smaller shape for *deciding* something. Both share `Portal` and
 * `useFocusTrap`, so they behave identically for a keyboard.
 *
 * `onConfirm` is optional: without it this is a plain container, and the caller
 * puts whatever controls it wants in `children`. */

import { useEffect, useState } from "react";
import { useLanguage } from "@/lib/language";
import { useFocusTrap } from "@/lib/hooks/use-focus-trap";
import Portal from "./portal";

export default function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  confirmLabel,
  onConfirm,
  confirmDisabled = false,
  destructive = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  confirmLabel?: string;
  onConfirm?: () => void;
  confirmDisabled?: boolean;
  destructive?: boolean;
}) {
  const { t } = useLanguage();
  // Callback ref into state, not useRef — see the note in sheet.tsx.
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

  return (
    <Portal>
      <div
        className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
        <div
          ref={setPanelEl}
          className="card relative w-full max-w-md animate-fadeIn border border-line/60 shadow-card-lg"
        >
          <h2 className="text-base font-bold">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          {children && <div className="mt-4">{children}</div>}
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn-ghost">
              {t("common.cancel")}
            </button>
            {onConfirm && (
              <button
                type="button"
                onClick={onConfirm}
                disabled={confirmDisabled}
                className={destructive ? "btn bg-danger text-white hover:brightness-95" : "btn-primary"}
              >
                {confirmLabel ?? t("common.confirm")}
              </button>
            )}
          </div>
        </div>
      </div>
    </Portal>
  );
}
