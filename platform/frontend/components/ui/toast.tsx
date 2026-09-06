"use client";

/** Minimal toast provider — mutation feedback (a 409 double-book must be
 * visible). No existing toast primitive in this repo.
 *
 * A toast may carry one action. That exists for undo: the task inbox removes a
 * resolved or dismissed row optimistically, and an undo button in the toast is
 * what makes that safe to do — otherwise a mis-tap on a phone silently closes
 * clinical work with no way back short of a filter change. Clicking the action
 * dismisses the toast, since the thing it was reporting no longer holds. */

import { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastOptions {
  action?: ToastAction;
  /** Undo needs longer than a plain confirmation to be reachable. */
  durationMs?: number;
}

interface Toast {
  id: number;
  message: string;
  kind: "success" | "error";
  action?: ToastAction;
}

const DEFAULT_DURATION_MS = 4000;

const ToastContext = createContext<{
  show: (message: string, kind?: Toast["kind"], options?: ToastOptions) => void;
} | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (message: string, kind: Toast["kind"] = "success", options?: ToastOptions) => {
      const id = Date.now() + Math.random();
      setToasts((prev) => [...prev, { id, message, kind, action: options?.action }]);
      setTimeout(() => dismiss(id), options?.durationMs ?? DEFAULT_DURATION_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div
        className="pointer-events-none fixed bottom-20 right-4 z-[100] flex flex-col gap-2 md:bottom-4"
        role="status"
        aria-live="polite"
      >
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
            <span className="min-w-0">{t.message}</span>
            {t.action && (
              <button
                type="button"
                onClick={() => {
                  t.action!.onClick();
                  dismiss(t.id);
                }}
                className="ml-2 shrink-0 rounded-xl px-2 py-1 text-sm font-semibold text-primary hover:bg-primary-soft"
              >
                {t.action.label}
              </button>
            )}
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
