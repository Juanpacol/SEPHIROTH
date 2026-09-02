"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Sheet from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type ShareableEvent } from "@/lib/api";
import { useLanguage } from "@/lib/language";

export default function ShareResultSheet({
  open,
  onClose,
  patientId,
}: {
  open: boolean;
  onClose: () => void;
  patientId: string;
}) {
  const queryClient = useQueryClient();
  const showToast = useToast();
  const { t } = useLanguage();
  const [selected, setSelected] = useState<ShareableEvent | null>(null);
  const [message, setMessage] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const { data: events } = useQuery({
    queryKey: ["results", "shareable", patientId],
    queryFn: () => api.shareableEvents(patientId),
    enabled: open,
  });

  const share = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const created = await api.createShare({
        patient_id: patientId,
        timeline_event_id: selected.timeline_event_id,
        message,
      });
      if (file) await api.uploadAttachment(created.id, file);
      await queryClient.invalidateQueries({ queryKey: ["results", "shareable", patientId] });
      showToast(t("shareResult.shared"));
      setSelected(null);
      setMessage("");
      setFile(null);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        showToast(t("shareResult.error.alreadyShared"), "error");
      } else {
        showToast(t("shareResult.error.shareFailed"), "error");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("shareResult.title")}>
      <div className="space-y-4">
        {!selected ? (
          <div className="space-y-2">
            {(events ?? []).length === 0 && (
              <p className="text-sm text-muted">{t("shareResult.empty")}</p>
            )}
            {(events ?? []).map((e) => (
              <button
                key={e.timeline_event_id}
                onClick={() => !e.already_shared && setSelected(e)}
                disabled={e.already_shared}
                className="card block w-full py-3 text-left disabled:cursor-not-allowed disabled:opacity-50"
              >
                <div className="text-sm font-semibold">{e.title}</div>
                <div className="text-xs text-muted">
                  {e.date} · {e.type}
                  {e.already_shared ? ` · ${t("shareResult.alreadyShared")}` : ""}
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="card py-3">
              <div className="text-sm font-semibold">{selected.title}</div>
              <div className="text-xs text-muted">{selected.date}</div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-semibold">{t("shareResult.message")}</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
                placeholder={t("shareResult.messagePlaceholder")}
                className="input"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-semibold">{t("shareResult.attachment")}</label>
              <input
                type="file"
                accept="application/pdf,image/png,image/jpeg"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button onClick={() => setSelected(null)} className="btn-ghost flex-1">
                {t("shareResult.back")}
              </button>
              <button onClick={share} disabled={busy} className="btn-primary flex-1">
                {busy ? t("shareResult.sharing") : t("shareResult.share")}
              </button>
            </div>
          </div>
        )}
      </div>
    </Sheet>
  );
}
