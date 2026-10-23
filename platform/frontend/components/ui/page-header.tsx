"use client";

/** The head of a section's page, in the landing's manner: a mono label, the title in the display face with
 * its last word in the accent, a line under it, and room on the right for the page's main action. */
import type { ReactNode } from "react";
import AccentTitle from "@/components/landing/accent-title";

export default function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  accentWords = 1,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  accentWords?: number;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow text-primary-ink">{eyebrow}</div>}
        <AccentTitle
          as="h1"
          text={title}
          accentWords={accentWords}
          accentClass="text-primary-ink"
          className="mt-0.5 text-4xl sm:text-5xl"
        />
        {subtitle && <p className="mt-2 max-w-xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2 pb-1">{actions}</div>}
    </header>
  );
}
