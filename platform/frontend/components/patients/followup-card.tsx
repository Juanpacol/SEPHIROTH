"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";
import { api, type FollowupPlan } from "@/lib/api";
import { useToast } from "@/components/ui/toast";

export default function FollowupCard({ patientId }: { patientId: string }) {
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
      showToast("Follow-up plan created — day 3/7/30 checks enrolled.");
    },
    onError: () => showToast("Could not create the follow-up plan — try again.", "error"),
  });

  const cancel = useMutation({
    mutationFn: (planId: string) => api.cancelFollowupPlan(planId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["followup-plans", patientId] }),
    onError: () => showToast("Could not cancel the plan — try again.", "error"),
  });

  const activePlan: FollowupPlan | undefined = plans?.[0];

  return (
    <div className="card">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-bold">
          <ClipboardCheck size={16} className="text-primary" /> Follow-up plan
        </h2>
      </div>

      {activePlan ? (
        <div className="space-y-2">
          <p className="text-sm text-ink/80">{activePlan.instructions || "(no instructions given)"}</p>
          <p className="text-xs text-muted">
            Active — day 3/7/30 check-ins enrolled since{" "}
            {new Date(activePlan.created_at).toLocaleDateString()}
          </p>
          <button
            onClick={() => cancel.mutate(activePlan.id)}
            disabled={cancel.isPending}
            className="text-xs font-semibold text-danger"
          >
            Cancel plan
          </button>
        </div>
      ) : (
        <div>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={2}
            placeholder="What should the day 3/7/30 check-ins ask about?"
            className="w-full resize-y rounded-xl border border-line/70 p-3 text-sm outline-none focus:border-primary"
          />
          <div className="mt-2 flex justify-end">
            <button
              onClick={() => create.mutate()}
              disabled={create.isPending}
              className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
            >
              {create.isPending ? "Creating…" : "Start follow-up plan"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
