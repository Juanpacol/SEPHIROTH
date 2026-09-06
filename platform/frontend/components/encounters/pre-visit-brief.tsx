"use client";

/** What the clinician needs before the patient sits down.
 *
 * Ordered by what gets looked at first: why they are here, what is unresolved,
 * what came back since the last visit, what they are taking. Nothing here is
 * inferred — every line is a row somebody already wrote, and the value is that
 * they are in one place.
 *
 * Collapsed by default on a phone, because during a visit the note is what the
 * screen is for and the brief is what you check before it starts.
 */

import { useState } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";

import { type PreVisitBrief } from "@/lib/api";
import { useLanguage } from "@/lib/language";

function Chips({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-ink/60">{label}</p>
      <ul className="mt-1 flex flex-wrap gap-1">
        {items.map((item) => (
          <li key={item} className="rounded-full bg-surface px-2 py-0.5 text-xs">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function PreVisitBriefPanel({ brief }: { brief: PreVisitBrief }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);

  const urgent = brief.open_tasks.filter((task) => task.overdue).length;

  return (
    <section className="card">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="tap flex w-full items-center justify-between gap-2 text-left md:cursor-default"
      >
        <span className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold">{t("encounter.brief.title")}</h2>
          {urgent > 0 ? (
            <span className="rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">
              {t("encounter.brief.overdue").replace("{count}", String(urgent))}
            </span>
          ) : null}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-ink/40 transition-transform md:hidden ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      <div className={`${open ? "flex" : "hidden"} mt-3 flex-col gap-4 md:flex`}>
        {brief.reason ? (
          <p className="text-sm">
            <span className="text-ink/60">{t("encounter.brief.reason")}: </span>
            {brief.reason}
          </p>
        ) : null}

        {brief.alerts.length > 0 || brief.risk_flags.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-ink/60">{t("encounter.brief.attention")}</p>
            <ul className="mt-1 flex flex-col gap-1">
              {brief.alerts.map((alert) => (
                <li key={alert.id} className="text-sm">
                  <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-danger align-middle" />
                  {alert.title}
                </li>
              ))}
              {brief.risk_flags.map((flag) => (
                <li key={flag.rule_key} className="text-sm text-ink/80">
                  <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-warning align-middle" />
                  {flag.detail}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {brief.open_tasks.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-ink/60">{t("encounter.brief.openWork")}</p>
            <ul className="mt-1 flex flex-col gap-1">
              {brief.open_tasks.slice(0, 6).map((task) => (
                <li key={task.id} className="text-sm">
                  <Link href={`/tasks?patient_id=${brief.patient.id}`} className="hover:underline">
                    {task.title}
                  </Link>
                  {task.overdue ? <span className="ml-1.5 text-xs text-danger">·</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {brief.recent_results.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-ink/60">{t("encounter.brief.results")}</p>
            <ul className="mt-1 flex flex-col gap-1">
              {brief.recent_results.map((result) => (
                <li key={`${result.kind}-${result.name}-${result.date}`} className="text-sm">
                  <span className={result.critical ? "font-medium text-danger" : ""}>
                    {result.name}
                  </span>
                  <span className="text-ink/60"> · {result.value}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {brief.recent_encounters.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-ink/60">{t("encounter.brief.lastVisits")}</p>
            <ul className="mt-1 flex flex-col gap-2">
              {brief.recent_encounters.map((visit) => (
                <li key={visit.id} className="text-sm">
                  <Link href={`/encounters/${visit.id}`} className="hover:underline">
                    {new Date(visit.started_at).toLocaleDateString()} — {visit.chief_complaint || "—"}
                  </Link>
                  {visit.assessment ? (
                    <p className="text-xs text-ink/60">{visit.assessment}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex flex-col gap-3">
          <Chips label={t("encounter.brief.allergies")} items={brief.allergies} />
          <Chips label={t("encounter.brief.medications")} items={brief.medications} />
          <Chips label={t("encounter.brief.conditions")} items={brief.conditions} />
        </div>
      </div>
    </section>
  );
}
