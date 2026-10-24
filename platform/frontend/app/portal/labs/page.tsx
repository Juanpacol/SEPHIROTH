"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import LabResultCard from "@/components/portal/lab-result-card";
import PageHeader from "@/components/ui/page-header";

/** The lab results a clinician reviewed and told this patient about, and
 * nothing else. */
export default function PortalLabsPage() {
  const { t } = useLanguage();
  const { data, isLoading, error } = useQuery({ queryKey: ["portal", "labs"], queryFn: api.portalLabs });
  const labs = data?.labs ?? [];

  return (
    <div className="space-y-5">
      <PageHeader eyebrow={t("portal.eyebrow")} title={t("portal.labs.title")} subtitle={t("portal.labs.subtitle")} />

      {isLoading ? <p className="text-sm text-muted">{t("portal.labs.loading")}</p> : null}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {t("portal.labs.error")}
        </p>
      ) : null}
      {!isLoading && !error && labs.length === 0 ? <p className="text-sm text-muted">{t("portal.labs.empty")}</p> : null}

      <ul className="space-y-3">
        {labs.map((lab) => (
          <li key={lab.share_id} className="card">
            {!lab.viewed_at ? (
              <span className="mb-2 inline-block rounded-full bg-primary px-2 py-0.5 text-[11px] font-semibold text-white">
                {t("portal.labs.new")}
              </span>
            ) : null}
            <LabResultCard lab={lab} />
            <Link
              href={`/portal/results/${lab.share_id}`}
              className="tap mt-3 inline-flex items-center text-sm font-semibold text-primary"
            >
              {t("portal.labs.open")}
            </Link>
          </li>
        ))}
      </ul>

      {labs.length > 0 ? <p className="text-xs text-muted">{t("portal.labs.disclaimer")}</p> : null}
    </div>
  );
}
