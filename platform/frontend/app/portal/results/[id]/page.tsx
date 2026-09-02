"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Download, FileDown, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";

export default function PortalResultDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useLanguage();
  const showToast = useToast();
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const { data: share, isLoading, error } = useQuery({
    queryKey: ["portal", "share", id],
    queryFn: () => api.getShare(id),
  });

  const downloadPdf = async () => {
    if (!share || downloadingPdf) return;
    setDownloadingPdf(true);
    try {
      const blob = await api.downloadSharePdf(share.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `resultado-${share.id.slice(0, 8)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      showToast(t("portal.result.error.downloadPdf"), "error");
    } finally {
      setDownloadingPdf(false);
    }
  };

  if (isLoading) return <p className="text-sm text-muted">{t("portal.results.loading")}</p>;
  if (error || !share) return <p className="text-sm text-danger">{t("portal.results.notFound")}</p>;

  return (
    <div className="max-w-2xl space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">{share.event.title}</h1>
          <p className="text-sm text-muted">{share.event.date}</p>
        </div>
        <button
          onClick={downloadPdf}
          disabled={downloadingPdf}
          className="flex shrink-0 items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-xs font-semibold text-ink/80 hover:bg-surface disabled:opacity-40"
        >
          {downloadingPdf ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
          {downloadingPdf ? t("portal.result.downloadingPdf") : t("portal.result.downloadPdf")}
        </button>
      </div>

      {share.message && (
        <div className="card border border-primary/20 bg-primary-soft/60">
          <div className="mb-1 text-xs font-semibold uppercase text-primary">{t("portal.results.fromClinician")}</div>
          <p className="text-sm">{share.message}</p>
        </div>
      )}

      <div className="card">
        {share.event.ai_generated && (
          <div className="mb-3">
            <AgentBadge name={t("portal.results.aiDrafted")} />
            <p className="mt-1 text-xs text-muted">{t("portal.results.aiDraftedNote")}</p>
          </div>
        )}
        <p className="whitespace-pre-wrap text-sm">{share.event.detail}</p>
      </div>

      {share.attachments.length > 0 && (
        <div className="card">
          <div className="mb-2 text-sm font-semibold">{t("portal.results.attachments")}</div>
          <ul className="space-y-2">
            {share.attachments.map((att) => (
              <li key={att.id}>
                <button
                  onClick={async () => {
                    const blob = await api.downloadAttachment(att.id);
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = att.filename;
                    link.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
                >
                  <Download size={16} />
                  {att.filename}
                  <span className="text-xs font-normal text-muted">
                    ({Math.round(att.size_bytes / 1024)} KB)
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
