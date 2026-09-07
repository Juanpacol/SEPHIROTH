"use client";

/** Orders decided in the room.
 *
 * Each becomes a task in the inbox when the visit is signed — never before. A
 * task created from an unsigned decision is work nobody committed to, and the
 * inbox is only worth reading because everything in it is real. The list says
 * so explicitly rather than leaving the clinician to infer it.
 */

import { useState } from "react";
import { Trash2 } from "lucide-react";

import { type EncounterOrder, type OrderKind } from "@/lib/api";
import { useLanguage } from "@/lib/language";

const KINDS: OrderKind[] = ["lab", "imaging", "referral", "followup", "medication"];

interface Props {
  orders: EncounterOrder[];
  disabled?: boolean;
  onAdd: (order: { kind: OrderKind; detail: string; due_in_days: number | null }) => void;
  onRemove: (orderId: string) => void;
}

export default function OrdersEditor({ orders, disabled, onAdd, onRemove }: Props) {
  const { t } = useLanguage();
  const [kind, setKind] = useState<OrderKind>("lab");
  const [detail, setDetail] = useState("");
  const [days, setDays] = useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!detail.trim()) return;
    onAdd({ kind, detail: detail.trim(), due_in_days: days === "" ? null : Number(days) });
    setDetail("");
    setDays("");
  }

  return (
    <section className="card flex flex-col gap-3">
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("encounter.orders.title")}</h2>
        <span className="text-xs text-ink/50">{t("encounter.orders.filedOnSign")}</span>
      </header>

      {orders.length === 0 ? (
        <p className="text-sm text-ink/50">{t("encounter.orders.empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {orders.map((order) => (
            <li key={order.id} className="flex items-start justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="text-sm">
                  <span className="font-medium">{t(`encounter.orderKind.${order.kind}`)}:</span>{" "}
                  {order.detail}
                </p>
                <p className="text-xs text-ink/50">
                  {order.due_in_days
                    ? t("encounter.orders.dueInDays").replace("{days}", String(order.due_in_days))
                    : t("encounter.orders.noDeadline")}
                  {order.task_id ? ` · ${t("encounter.orders.filed")}` : ""}
                </p>
              </div>
              {!disabled && !order.task_id ? (
                <button
                  type="button"
                  onClick={() => onRemove(order.id)}
                  aria-label={t("encounter.orders.remove")}
                  className="tap rounded-md p-1.5 text-ink/50 hover:bg-surface hover:text-danger"
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {!disabled ? (
        <form onSubmit={submit} className="flex flex-col gap-2 border-t border-border pt-3 sm:flex-row">
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as OrderKind)}
            aria-label={t("encounter.orders.kind")}
            className="tap rounded-lg border border-border bg-white px-3 py-2 text-sm sm:w-40"
          >
            {KINDS.map((option) => (
              <option key={option} value={option}>
                {t(`encounter.orderKind.${option}`)}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={detail}
            onChange={(event) => setDetail(event.target.value)}
            placeholder={t("encounter.orders.detailPlaceholder")}
            aria-label={t("encounter.orders.detail")}
            className="tap min-w-0 flex-1 rounded-lg border border-border bg-white px-3 py-2 text-sm"
          />
          <input
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(event) => setDays(event.target.value)}
            placeholder={t("encounter.orders.daysPlaceholder")}
            aria-label={t("encounter.orders.days")}
            className="tap rounded-lg border border-border bg-white px-3 py-2 text-sm sm:w-28"
          />
          <button type="submit" disabled={!detail.trim()} className="btn-secondary tap disabled:opacity-50">
            {t("encounter.orders.add")}
          </button>
        </form>
      ) : null}
    </section>
  );
}
