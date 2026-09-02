"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FileText, Paperclip } from "lucide-react";
import { api } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";
import { useLanguage } from "@/lib/language";

export default function PortalResultsPage() {
  const { t } = useLanguage();
  const { data: shares, isLoading } = useQuery({
    queryKey: ["portal", "shares"],
    queryFn: () => api.listShares(),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t("portal.results.title")}</h1>

      {isLoading && <p className="text-sm text-muted">{t("portal.results.loading")}</p>}
      {!isLoading && (shares ?? []).length === 0 && (
        <p className="text-sm text-muted">{t("portal.results.empty")}</p>
      )}

      <div className="space-y-3">
        {(shares ?? []).map((share) => (
          <Link
            key={share.id}
            href={`/portal/results/${share.id}`}
            className="card flex items-center justify-between transition-colors hover:bg-primary-soft/40"
          >
            <div className="flex items-center gap-3">
              <FileText size={18} className="shrink-0 text-primary" />
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {share.event.title}
                  {!share.viewed_at && (
                    <span className="h-2 w-2 rounded-full bg-primary" aria-label={t("portal.results.unread")} />
                  )}
                  {share.event.ai_generated && <AgentBadge name={t("portal.results.aiDrafted")} />}
                </div>
                <div className="text-xs text-muted">{share.event.date}</div>
              </div>
            </div>
            {share.attachments.length > 0 && (
              <div className="flex items-center gap-1 text-xs text-muted">
                <Paperclip size={14} /> {share.attachments.length}
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
