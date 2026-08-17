"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FileText, Paperclip } from "lucide-react";
import { api } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";

export default function PortalResultsPage() {
  const { data: shares, isLoading } = useQuery({
    queryKey: ["portal", "shares"],
    queryFn: () => api.listShares(),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">My Results</h1>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {!isLoading && (shares ?? []).length === 0 && (
        <p className="text-sm text-muted">No results have been shared with you yet.</p>
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
                    <span className="h-2 w-2 rounded-full bg-primary" aria-label="Unread" />
                  )}
                  {share.event.ai_generated && <AgentBadge name="AI-drafted" />}
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
