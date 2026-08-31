"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, TrendingUp } from "lucide-react";
import { api, type HistoryItem } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import AgentBadge from "@/components/agent-badge";

function RecommendationRow({ item }: { item: HistoryItem }) {
  const { t } = useLanguage();
  const OUTCOMES: { value: "improved" | "not_improved" | "unclear"; label: string }[] = [
    { value: "improved", label: t("recommendations.outcome.improved") },
    { value: "not_improved", label: t("recommendations.outcome.notImproved") },
    { value: "unclear", label: t("recommendations.outcome.unclear") },
  ];
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["history"] });
    queryClient.invalidateQueries({ queryKey: ["recommendation-stats"] });
  };

  const toggleActedOn = async () => {
    await api.markActedOn(item.id, !item.acted_on);
    invalidate();
  };

  const setOutcome = async (outcome: "improved" | "not_improved" | "unclear") => {
    await api.markOutcome(item.id, outcome);
    invalidate();
  };

  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {item.agents_involved?.map((agent) => (
            <AgentBadge key={agent} name={agent} />
          ))}
          <span className="text-xs text-muted">{new Date(item.created_at).toLocaleString()}</span>
        </div>
        <span className="text-xs text-muted">
          {item.patient_id
            ? t("recommendations.patientLabel").replace("{id}", item.patient_id)
            : t("recommendations.generalQuestion")}
        </span>
      </div>

      <div className="text-sm font-semibold">{item.query}</div>
      <div className="line-clamp-3 whitespace-pre-wrap text-sm text-muted">{item.answer}</div>

      <div className="flex flex-wrap items-center gap-3 border-t border-line/60 pt-3">
        <button
          onClick={toggleActedOn}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
            item.acted_on ? "bg-success/10 text-success" : "bg-surface text-muted hover:text-primary"
          }`}
        >
          {item.acted_on ? <CheckCircle2 size={14} /> : <Circle size={14} />}
          {item.acted_on ? t("recommendations.actedOn") : t("recommendations.actOnThis")}
        </button>

        {item.acted_on && (
          <div className="flex items-center gap-1.5">
            {OUTCOMES.map((o) => (
              <button
                key={o.value}
                onClick={() => setOutcome(o.value)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                  item.outcome === o.value
                    ? "bg-primary text-white"
                    : "bg-surface text-muted hover:text-primary"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function RecommendationsPage() {
  const { t } = useLanguage();
  const { data: history, isLoading } = useQuery({ queryKey: ["history"], queryFn: api.history });
  const { data: stats } = useQuery({
    queryKey: ["recommendation-stats"],
    queryFn: api.recommendationStats,
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("nav.recommendations")}</h1>
        <p className="text-sm text-muted">{t("recommendations.subtitle")}</p>
      </div>

      {stats && (
        <div className="card flex items-center gap-3">
          <TrendingUp size={18} className="text-primary" />
          <p className="text-sm">
            {t("recommendations.stats.actedOnLead")}{" "}
            <span className="font-bold">{stats.acted_on}</span> {t("recommendations.stats.of")}{" "}
            <span className="font-bold">{stats.total}</span> {t("recommendations.stats.total")}
            {stats.acted_on > 0 && (
              <>
                {" · "}
                {t("recommendations.stats.improvedNote").replace(
                  "{count}",
                  String(stats.improved)
                )}
              </>
            )}
          </p>
        </div>
      )}

      {isLoading && <div className="text-muted">{t("common.loading")}</div>}
      {!isLoading && (!history || history.length === 0) && (
        <div className="card text-muted">{t("recommendations.empty")}</div>
      )}

      <div className="space-y-4">
        {history?.map((item) => (
          <RecommendationRow key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
