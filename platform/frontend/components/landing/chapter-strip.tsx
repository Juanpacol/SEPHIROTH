"use client";

/** What SEPHIROTH has, as one row of icons you choose from and one panel that says what the
 * chosen one does: the three specialists, then the work around a consultation. It replaces
 * two sections of cards, in the manner of the chapter strip at the top of Apple's product
 * pages. A tab list, so the arrow keys move along it. */

import { useState, type KeyboardEvent } from "react";
import type { LucideIcon } from "lucide-react";
import { ScanEye, Pill, BookOpen, LayoutDashboard, CalendarClock, UserCheck, Share2 } from "lucide-react";
import { useLanguage } from "@/lib/language";

const CHAPTERS: {
  id: string;
  Icon: LucideIcon;
  titleKey: string;
  bodyKey: string;
  group: "agent" | "platform";
}[] = [
  {
    id: "radiology",
    Icon: ScanEye,
    titleKey: "marketing.agentName.radiology",
    bodyKey: "marketing.agentsSection.radiology.body",
    group: "agent",
  },
  {
    id: "drug-safety",
    Icon: Pill,
    titleKey: "marketing.agentName.drugSafety",
    bodyKey: "marketing.agentsSection.drugSafety.body",
    group: "agent",
  },
  {
    id: "evidence",
    Icon: BookOpen,
    titleKey: "marketing.agentName.evidence",
    bodyKey: "marketing.agentsSection.evidence.body",
    group: "agent",
  },
  {
    id: "dashboard",
    Icon: LayoutDashboard,
    titleKey: "marketing.platform.dashboard.title",
    bodyKey: "marketing.platform.dashboard.body",
    group: "platform",
  },
  {
    id: "scheduling",
    Icon: CalendarClock,
    titleKey: "marketing.platform.scheduling.title",
    bodyKey: "marketing.platform.scheduling.body",
    group: "platform",
  },
  {
    id: "portal",
    Icon: UserCheck,
    titleKey: "marketing.platform.portal.title",
    bodyKey: "marketing.platform.portal.body",
    group: "platform",
  },
  {
    id: "results",
    Icon: Share2,
    titleKey: "marketing.platform.results.title",
    bodyKey: "marketing.platform.results.body",
    group: "platform",
  },
];

export default function ChapterStrip() {
  const { t } = useLanguage();
  const [index, setIndex] = useState(0);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (index + step + CHAPTERS.length) % CHAPTERS.length;
    setIndex(next);
    document.getElementById(`chapter-tab-${CHAPTERS[next].id}`)?.focus();
  };

  return (
    <div>
      <div
        role="tablist"
        aria-label={t("marketing.chapters.label")}
        onKeyDown={onKeyDown}
        className="-mx-6 flex snap-x gap-2 overflow-x-auto px-6 pb-2 [scrollbar-width:none] md:mx-0 md:grid md:grid-cols-7 md:px-0 [&::-webkit-scrollbar]:hidden"
      >
        {CHAPTERS.map(({ id, Icon, titleKey, group }, i) => (
          <button
            key={id}
            id={`chapter-tab-${id}`}
            role="tab"
            aria-selected={i === index}
            aria-controls="chapter-panel"
            tabIndex={i === index ? 0 : -1}
            data-group={group}
            onClick={() => setIndex(i)}
            className="tap group flex w-28 shrink-0 snap-start flex-col items-center gap-3 rounded-2xl px-2 py-4 text-center text-sm font-semibold transition-colors duration-normal ease-standard md:w-auto aria-selected:bg-card aria-selected:shadow-raised"
          >
            <span className="inline-flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary-ink transition-transform duration-slow ease-emphasized group-aria-selected:scale-110">
              <Icon size={26} aria-hidden="true" />
            </span>
            <span className="text-balance leading-tight text-muted group-aria-selected:text-ink">
              {t(titleKey)}
            </span>
          </button>
        ))}
      </div>

      <div
        id="chapter-panel"
        role="tabpanel"
        aria-labelledby={`chapter-tab-${CHAPTERS[index].id}`}
        className="mt-6 rounded-[28px] border border-line/60 bg-card p-8 shadow-raised md:p-12"
      >
        <div key={CHAPTERS[index].id} className="animate-fadeIn motion-reduce:animate-none">
          <span className="eyebrow text-primary-ink">
            {t(
              CHAPTERS[index].group === "agent" ? "marketing.chapters.agent" : "marketing.chapters.platform",
            )}
          </span>
          <h3 className="mt-3 font-display text-[clamp(2rem,1.4rem+2vw,3.25rem)] font-light leading-[1.05]">
            {t(CHAPTERS[index].titleKey)}
          </h3>
          <p className="mt-5 max-w-2xl text-lg font-light leading-relaxed text-ink/90">
            {t(CHAPTERS[index].bodyKey)}
          </p>
        </div>
      </div>
    </div>
  );
}
