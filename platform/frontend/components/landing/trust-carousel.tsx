"use client";

/** The three safeguards as large cards in a row you move through sideways, the way Apple lays
 * out a product's highlights: scroll-snap, with arrows for a mouse. Each card holds the
 * interactive demonstration that used to sit loose in the page. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useLanguage } from "@/lib/language";
import ClaimVerifier from "./claim-verifier";
import CitationGuardToggle from "./citation-guard-toggle";
import AbstentionGate from "./abstention-gate";

const CARDS: { id: string; titleKey: string; bodyKey: string; demo: ReactNode }[] = [
  {
    id: "citations",
    titleKey: "marketing.safeguards.citationGuardTitle",
    bodyKey: "marketing.safeguards.citationGuardBody",
    demo: <CitationGuardToggle />,
  },
  {
    id: "claims",
    titleKey: "marketing.safeguards.claimVerifierTitle",
    bodyKey: "marketing.safeguards.claimVerifierBody",
    demo: <ClaimVerifier />,
  },
  {
    id: "abstain",
    titleKey: "marketing.safeguards.abstentionGateTitle",
    bodyKey: "marketing.safeguards.abstentionGateBody",
    demo: <AbstentionGate />,
  },
];

export default function TrustCarousel() {
  const { t } = useLanguage();
  const track = useRef<HTMLUListElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });

  const measure = useCallback(() => {
    const el = track.current;
    if (!el) return;
    setEdge({ start: el.scrollLeft <= 4, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 4 });
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const move = (direction: 1 | -1) => {
    const el = track.current;
    const card = el?.querySelector("li");
    if (!el || !card) return;
    el.scrollBy({ left: direction * (card.clientWidth + 24), behavior: "smooth" });
  };

  return (
    <div>
      <ul
        ref={track}
        onScroll={measure}
        aria-label={t("marketing.safeguards.title")}
        className="-mx-6 flex snap-x snap-mandatory scroll-px-6 gap-6 overflow-x-auto px-6 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {CARDS.map((card) => (
          <li
            key={card.id}
            data-trust-card={card.id}
            className="w-[min(88vw,38rem)] shrink-0 snap-center rounded-[28px] border border-line/60 bg-card p-6 shadow-raised md:snap-start md:p-10"
          >
            <h3 className="font-display text-[clamp(1.75rem,1.2rem+1.6vw,2.5rem)] font-light leading-[1.05]">
              {t(card.titleKey)}
            </h3>
            <p className="mb-6 mt-3 text-muted">{t(card.bodyKey)}</p>
            {card.demo}
          </li>
        ))}
      </ul>
      <div className="mt-4 flex justify-end gap-3">
        <button
          type="button"
          onClick={() => move(-1)}
          disabled={edge.start}
          aria-label={t("marketing.carousel.previous")}
          className="tap btn-secondary size-11 justify-center rounded-full p-0 disabled:opacity-40"
        >
          <ChevronLeft size={20} />
        </button>
        <button
          type="button"
          onClick={() => move(1)}
          disabled={edge.end}
          aria-label={t("marketing.carousel.next")}
          className="tap btn-secondary size-11 justify-center rounded-full p-0 disabled:opacity-40"
        >
          <ChevronRight size={20} />
        </button>
      </div>
    </div>
  );
}
