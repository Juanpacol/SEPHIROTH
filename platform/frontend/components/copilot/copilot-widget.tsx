"use client";

/** Global floating launcher for Copilot Chat — replaces the old dedicated
 * `/copilot` page so a clinician never has to leave whatever patient/page
 * they're on to ask a question. Mounted once in AppShell, so it's present
 * (and its conversation state persists) across every chrome'd route. */

import { useState } from "react";
import { Bot, X } from "lucide-react";
import { useUser } from "@/lib/auth";
import CopilotPanel from "@/components/copilot/copilot-panel";

export default function CopilotWidget() {
  const user = useUser();
  const [open, setOpen] = useState(false);

  // Copilot is a clinician tool — patients have their own portal, not this.
  if (user?.role === "patient") return null;

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close Copilot Chat" : "Open Copilot Chat"}
        aria-expanded={open}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-white shadow-card-lg transition-all duration-200 ease-ios hover:-translate-y-0.5 hover:bg-primary-dark active:scale-95"
      >
        {open ? <X size={22} /> : <Bot size={22} />}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Copilot Chat"
          className="fixed bottom-24 right-6 z-40 flex h-[min(680px,calc(100vh-140px))] w-[min(420px,calc(100vw-3rem))] flex-col overflow-hidden rounded-squircle border border-line/60 bg-surface shadow-card-lg"
        >
          <div className="flex items-center justify-between border-b border-line/60 bg-card px-4 py-3">
            <div>
              <h2 className="text-sm font-bold">Copilot Chat</h2>
              <p className="text-xs text-muted">Every citation verified against tool output.</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="rounded-full p-1.5 text-muted hover:bg-surface hover:text-primary"
            >
              <X size={16} />
            </button>
          </div>
          <div className="min-h-0 flex-1 p-3">
            <CopilotPanel />
          </div>
        </div>
      )}
    </>
  );
}
