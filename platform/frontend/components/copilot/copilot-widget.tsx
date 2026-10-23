"use client";

/** Global floating launcher for Copilot Chat — replaces the old dedicated
 * `/copilot` page so a clinician never has to leave whatever patient/page
 * they're on to ask a question. Mounted once in AppShell, so it's present
 * (and its conversation state persists) across every chrome'd route. */

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useUser } from "@/lib/auth";
import CopilotPanel from "@/components/copilot/copilot-panel";
import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";

/** Custom-event name other pages (e.g. `/imaging`'s "Ask SEPHIROTH" button)
 * dispatch to open this widget with a pre-filled question — a plain
 * `window` event instead of a new state-management dependency, since the
 * widget already only needs to react to one thing from the outside. */
export const OPEN_COPILOT_EVENT = "open-copilot";

export default function CopilotWidget() {
  const user = useUser();
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [prefill, setPrefill] = useState("");
  // Bumped on every external open request so `<CopilotPanel key={...}>`
  // remounts with the new `initialQuery` — the panel owns its `query`
  // state internally and has no other way to be told "start over with
  // this text" once already mounted.
  const [prefillNonce, setPrefillNonce] = useState(0);

  useEffect(() => {
    const onOpenRequest = (e: Event) => {
      const detail = (e as CustomEvent<{ prefill?: string }>).detail;
      setPrefill(detail?.prefill ?? "");
      setPrefillNonce((n) => n + 1);
      setOpen(true);
    };
    window.addEventListener(OPEN_COPILOT_EVENT, onOpenRequest);
    return () => window.removeEventListener(OPEN_COPILOT_EVENT, onOpenRequest);
  }, []);

  // Copilot is a clinician tool — patients have their own portal, not this.
  if (user?.role === "patient") return null;

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? t("copilot.widget.closeChat") : t("copilot.widget.openChat")}
        aria-expanded={open}
        className="group fixed bottom-20 right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full border border-white/30 bg-[linear-gradient(145deg,#3a52b3_0%,#222d6b_55%,#171f4a_100%)] text-[#b6cfff] shadow-[inset_0_1px_0_rgb(255_255_255/0.4),0_12px_28px_-10px_rgb(31_46_102/0.9)] backdrop-blur-md transition-[transform,border-color,box-shadow] duration-300 ease-ios hover:-translate-y-0.5 hover:border-white/60 active:scale-95 md:bottom-6 md:right-6"
      >
        {!open && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-full bg-[#6f8bff]/25 motion-safe:animate-pulse"
          />
        )}
        <span className="relative transition-transform duration-300 ease-ios group-hover:-translate-y-px group-hover:rotate-[-6deg]">
          {open ? <X size={21} strokeWidth={1.75} /> : <WingMark size={24} />}
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t("copilot.widget.title")}
          className="fixed inset-0 z-50 flex flex-col overflow-hidden border-white/15 copilot-skin shadow-raised-lg md:inset-auto md:bottom-24 md:right-6 md:z-40 md:h-[min(680px,calc(100dvh-140px))] md:w-[min(420px,calc(100vw-3rem))] md:rounded-squircle md:border"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div className="flex items-center gap-2">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                style={{
                  background: "linear-gradient(135deg,#8C92AC,#D1D5DB)",
                }}
              >
                <WingMark size={16} className="text-white" />
              </span>
              <div>
                <h2 className="font-display text-lg font-light uppercase leading-none tracking-[0.12em]">
                  {t("copilot.widget.title")}
                </h2>
                <p className="mt-1 text-[11px] leading-tight text-muted">{t("copilot.widget.subtitle")}</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label={t("common.close")} className="tap rounded-full p-1.5 text-muted transition-colors duration-normal hover:text-primary-ink">
              <X size={16} strokeWidth={1.5} />
            </button>
          </div>
          <div className="min-h-0 flex-1 p-3">
            <CopilotPanel key={prefillNonce} initialQuery={prefill} />
          </div>
        </div>
      )}
    </>
  );
}
