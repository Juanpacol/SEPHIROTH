"use client";

/** Results, in two halves.
 *
 * The inbox leads, because "what has nobody read" is the question a clinic gets
 * sued over and the one this page previously could not answer at all. The share
 * list stays a tab away: what was sent and what is still unread is a different
 * question, and it already had a good answer.
 *
 * Telling the patient is done from here too (`InformPatientSheet`): the clinician
 * writes the message, and the server makes the entry the portal renders from the
 * result unless they pick one of the patient's own.
 */

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Disposition, type ResultReview } from "@/lib/api";
import { Search } from "lucide-react";
import { useLanguage } from "@/lib/language";
import FilterTabs from "@/components/ui/filter-tabs";
import PageHeader from "@/components/ui/page-header";
import PatientPicker from "@/components/copilot/patient-picker";
import InformPatientSheet from "@/components/results/inform-patient-sheet";
import ResultReviewCard from "@/components/results/result-review-card";
import SharedResultsList from "@/components/results/shared-results-list";

type Tab = "inbox" | "shared";
type Filter = "open" | "critical" | "closed";

const INBOX_QUERY_KEY = ["results", "inbox"] as const;

export default function ResultsPage() {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("inbox");
  // A link from a patient's lab card arrives with the patient and which list the
  // result is in already chosen.
  const linked = useSearchParams();
  const linkedFilter = linked.get("filter");
  const [filter, setFilter] = useState<Filter>(
    linkedFilter === "closed" || linkedFilter === "critical" ? linkedFilter : "open"
  );
  const [patientId, setPatientId] = useState(linked.get("patient") ?? "");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [informing, setInforming] = useState<ResultReview | null>(null);

  const params = useMemo(() => {
    const base: { status?: readonly ["closed"]; severity?: "critical"; patient_id?: string } = {};
    if (filter === "closed") base.status = ["closed"] as const;
    if (filter === "critical") base.severity = "critical";
    if (patientId) base.patient_id = patientId;
    return base;
  }, [filter, patientId]);

  const inbox = useQuery({
    queryKey: [...INBOX_QUERY_KEY, filter, patientId],
    queryFn: () => api.resultsInbox({ ...params, status: params.status ? [...params.status] : undefined }),
    enabled: tab === "inbox",
  });

  const patientsQuery = useQuery({
    queryKey: ["patients"],
    queryFn: () => api.patients(),
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
  const allItems = inbox.data?.items ?? [];
  const query = search.trim().toLowerCase();
  const items = query
    ? allItems.filter((item) =>
        [item.patient_name, item.result.test_name, item.classification_reason]
          .filter(Boolean)
          .some((field) => field!.toLowerCase().includes(query))
      )
    : allItems;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={t("patients.eyebrow")}
        title={t("results.title")}
        subtitle={t("results.inbox.subtitle")}
      />

      <FilterTabs
        label={t("results.title")}
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "inbox", label: t("results.tab.inbox") },
          { value: "shared", label: t("results.tab.shared") },
        ]}
      />

      {tab === "shared" ? (
        <SharedResultsList />
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <FilterTabs
              label={t("results.filter.open")}
              value={filter}
              onChange={setFilter}
              tabs={[
                { value: "open", label: t("results.filter.open") },
                { value: "critical", label: t("results.filter.critical"), dot: "bg-danger" },
                { value: "closed", label: t("results.filter.closed") },
              ]}
            />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <PatientPicker
                placement="down"
                patients={patientsQuery.data ?? []}
                value={patientId}
                onChange={setPatientId}
                noneLabel={t("results.filter.allPatients")}
              />
              <div className="relative w-full sm:w-64">
                <Search
                  size={14}
                  strokeWidth={1.5}
                  className="pointer-events-none absolute left-0 top-1/2 -translate-y-1/2 text-muted"
                />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("results.search.placeholder")}
                  aria-label={t("results.search.placeholder")}
                  className="w-full border-0 border-b border-line/60 bg-transparent py-2 pl-6 pr-1 text-sm text-ink transition-colors duration-normal placeholder:text-muted focus:border-primary-ink focus-visible:!outline-none"
                />
              </div>
            </div>
          </div>

          {error ? (
            <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}

          {inbox.isLoading ? (
            <div className="h-32 animate-pulse rounded-card bg-line/20" aria-busy="true" />
          ) : items.length === 0 ? (
            <p className="card text-sm text-muted">{t("results.inbox.empty")}</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {items.map((item) => (
                <ResultReviewCard
                  key={item.id}
                  review={item}
                  busy={busy}
                  onReview={(body) => review.mutate({ id: item.id, ...body })}
                  onCommunicate={() => setInforming(item)}
                  onClose={() => close.mutate(item.id)}
                  onReopen={() => reopen.mutate(item.id)}
                />
              ))}
            </div>
          )}
        </>
      )}
      <InformPatientSheet
        review={informing}
        onClose={() => setInforming(null)}
        onDone={(updated) => {
          settle(updated);
          setInforming(null);
        }}
      />
    </div>
  );
}
