"use client";

/** Minimal toast provider — mutation feedback (a 409 double-book must be
 * visible). No existing toast primitive in this repo. */

import { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

interface Toast {
  id: number;
  message: string;
  kind: "success" | "error";
}

const ToastContext = createContext<{ show: (message: string, kind?: Toast["kind"]) => void } | null>(
  null
);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, kind: Toast["kind"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, kind }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`card pointer-events-auto flex items-center gap-2 py-3 pr-4 text-sm font-medium shadow-card animate-fadeIn ${
              t.kind === "error" ? "text-danger" : "text-ink"
            }`}
          >
            {t.kind === "error" ? (
              <XCircle size={18} className="shrink-0" />
            ) : (
              <CheckCircle2 size={18} className="shrink-0 text-success" />
            )}
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx.show;
}
