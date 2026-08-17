"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";

export default function PortalResultDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: share, isLoading, error } = useQuery({
    queryKey: ["portal", "share", id],
    queryFn: () => api.getShare(id),
  });

  if (isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (error || !share) return <p className="text-sm text-danger">This result could not be found.</p>;

  return (
    <div className="max-w-2xl space-y-5">
      <div>
        <h1 className="text-lg font-bold">{share.event.title}</h1>
        <p className="text-sm text-muted">{share.event.date}</p>
      </div>

      {share.message && (
        <div className="card border border-primary/20 bg-primary-soft/60">
          <div className="mb-1 text-xs font-semibold uppercase text-primary">From your clinician</div>
          <p className="text-sm">{share.message}</p>
        </div>
      )}

      <div className="card">
        {share.event.ai_generated && (
          <div className="mb-3">
            <AgentBadge name="AI-drafted" />
            <p className="mt-1 text-xs text-muted">
              This summary was drafted by an AI agent and reviewed by your clinician before being
              shared with you.
            </p>
          </div>
        )}
        <p className="whitespace-pre-wrap text-sm">{share.event.detail}</p>
      </div>

      {share.attachments.length > 0 && (
        <div className="card">
          <div className="mb-2 text-sm font-semibold">Attachments</div>
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
