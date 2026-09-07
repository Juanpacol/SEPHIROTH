"use client";

/** Results, in two halves.
 *
 * The inbox leads, because "what has nobody read" is the question a clinic gets
 * sued over and the one this page previously could not answer at all. The share
 * list stays a tab away: what was sent and what is still unread is a different
 * question, and it already had a good answer.
 *
 * Communicating a result opens the patient's chart rather than sending from
 * here. The share needs the timeline entry the portal will render, and picking
 * that is a decision about which of a patient's entries this result *is* —
 * guessing it would show somebody the wrong result.
 */

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Disposition, type ResultReview } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import SegmentedControl from "@/components/ui/segmented-control";
import ResultReviewCard from "@/components/results/result-review-card";
import SharedResultsList from "@/components/results/shared-results-list";

type Tab = "inbox" | "shared";
type Filter = "open" | "critical" | "closed";

const INBOX_QUERY_KEY = ["results", "inbox"] as const;

export default function ResultsPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("inbox");
  const [filter, setFilter] = useState<Filter>("open");
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => {
    if (filter === "closed") return { status: ["closed"] as const };
    if (filter === "critical") return { severity: "critical" as const };
    return {};
  }, [filter]);

  const inbox = useQuery({
    queryKey: [...INBOX_QUERY_KEY, filter],
    queryFn: () => api.resultsInbox({ ...params, status: params.status ? [...params.status] : undefined }),
    enabled: tab === "inbox",
  });

  function settle(updated: ResultReview) {
    queryClient.invalidateQueries({ queryKey: INBOX_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["badges"] });
    setError(null);
    return updated;
  }

  const review = useMutation({
    mutationFn: ({ id, ...body }: { id: string; disposition: Disposition; note: string }) =>
      api.reviewResult(id, body),
    onSuccess: settle,
    onError: (err: Error) => setError(err.message),
  });

  const close = useMutation({
    mutationFn: (id: string) => api.closeResult(id),
    onSuccess: settle,
    onError: (err: Error) => setError(err.message),
  });

  const reopen = useMutation({
    mutationFn: (id: string) => api.reopenResult(id),
    onSuccess: settle,
    onError: (err: Error) => setError(err.message),
  });

  const busy = review.isPending || close.isPending || reopen.isPending;
  const items = inbox.data?.items ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("results.title")}</h1>
        <p className="text-sm text-muted">{t("results.inbox.subtitle")}</p>
      </div>

      <SegmentedControl
        label={t("results.title")}
        value={tab}
        onChange={(value) => setTab(value as Tab)}
        options={[
          { value: "inbox", label: t("results.tab.inbox") },
          { value: "shared", label: t("results.tab.shared") },
        ]}
      />

      {tab === "shared" ? (
        <SharedResultsList />
      ) : (
        <>
          <SegmentedControl
            label={t("results.filter.open")}
            value={filter}
            onChange={(value) => setFilter(value as Filter)}
            options={[
              { value: "open", label: t("results.filter.open") },
              { value: "critical", label: t("results.filter.critical") },
              { value: "closed", label: t("results.filter.closed") },
            ]}
          />

          {error ? (
            <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}

          {inbox.isLoading ? (
            <div className="h-32 animate-pulse rounded-xl bg-surface" aria-busy="true" />
          ) : items.length === 0 ? (
            <p className="card text-sm text-muted">{t("results.inbox.empty")}</p>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {items.map((item) => (
                <ResultReviewCard
                  key={item.id}
                  review={item}
                  busy={busy}
                  onReview={(body) => review.mutate({ id: item.id, ...body })}
                  onCommunicate={() => router.push(`/patients/${item.patient_id}`)}
                  onClose={() => close.mutate(item.id)}
                  onReopen={() => reopen.mutate(item.id)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
