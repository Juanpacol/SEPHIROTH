"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";
import { api, type FollowupPlan } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";

export default function FollowupCard({ patientId }: { patientId: string }) {
  const { t } = useLanguage();
  const [instructions, setInstructions] = useState("");
  const queryClient = useQueryClient();
  const showToast = useToast();

  const { data: plans } = useQuery({
    queryKey: ["followup-plans", patientId],
    queryFn: () => api.listFollowupPlans({ patient_id: patientId, status: "active" }),
  });

  const create = useMutation({
    mutationFn: () => api.createFollowupPlan({ patient_id: patientId, instructions }),
    onSuccess: () => {
      setInstructions("");
      queryClient.invalidateQueries({ queryKey: ["followup-plans", patientId] });
      showToast(t("patientDetail.followup.created"));
    },
    onError: () => showToast(t("patientDetail.followup.error.create"), "error"),
  });

  const cancel = useMutation({
    mutationFn: (planId: string) => api.cancelFollowupPlan(planId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["followup-plans", patientId] }),
    onError: () => showToast(t("patientDetail.followup.error.cancel"), "error"),
  });

  const activePlan: FollowupPlan | undefined = plans?.[0];

  return (
    <div className="card">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-bold">
          <ClipboardCheck size={16} className="text-primary" /> {t("patientDetail.followup.title")}
        </h2>
      </div>
      <p className="mb-3 text-xs text-muted">{t("patientDetail.followup.subtitle")}</p>

      {activePlan ? (
        <div className="space-y-2">
          <p className="text-sm text-ink/80">
            {activePlan.instructions || t("patientDetail.followup.noInstructions")}
          </p>
          <p className="text-xs text-muted">
            {t("patientDetail.followup.activeSince").replace(
              "{date}",
              new Date(activePlan.created_at).toLocaleDateString()
            )}
          </p>
          <button
            onClick={() => cancel.mutate(activePlan.id)}
            disabled={cancel.isPending}
            className="text-xs font-semibold text-danger"
          >
            {t("patientDetail.followup.cancelPlan")}
          </button>
        </div>
      ) : (
        <div>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={2}
            placeholder={t("patientDetail.followup.placeholder")}
            className="input resize-y rounded-xl p-3"
          />
          <div className="mt-2 flex justify-end">
            <button
              onClick={() => create.mutate()}
              disabled={create.isPending}
              className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
            >
              {create.isPending ? t("patientDetail.followup.creating") : t("patientDetail.followup.start")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
