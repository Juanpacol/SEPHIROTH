"use client";

/** A right-side drawer over a scrim — used for booking, editing working
 * hours, and sharing a result. No existing modal/dialog/drawer primitive
 * in this repo, so this is the first one; kept minimal (no portal, no
 * focus trap library) since Next's client tree already renders it above
 * everything else in normal DOM order. */

import { useEffect } from "react";
import { X } from "lucide-react";
import { useLanguage } from "@/lib/language";

export default function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const { t } = useLanguage();

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
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div className="glass-surface relative flex h-full w-full max-w-md flex-col border-l border-line/60 shadow-card animate-fadeIn">
        <div className="flex items-center justify-between border-b border-line/60 px-5 py-4">
          <h2 className="text-base font-bold">{title}</h2>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="rounded-full p-1.5 text-muted hover:bg-primary-soft"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
