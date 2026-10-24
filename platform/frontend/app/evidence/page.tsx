"use client";

/** A question box in the chat's manner (`.copilot-skin`), category tabs that share one content area with
 * search results, and evidence as cards with a mono source line and two actions — reading this and the
 * imaging page as one "AI content" idiom instead of two unrelated screens. */

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpenCheck, Check, Copy } from "lucide-react";
import { api, type EvidenceItem } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import FilterTabs from "@/components/ui/filter-tabs";
import PageHeader from "@/components/ui/page-header";
import { OPEN_COPILOT_EVENT } from "@/components/copilot/copilot-widget";

const EXAMPLE_KEYS = ["evidence.example.bp", "evidence.example.a1c", "evidence.example.interaction"] as const;

function CopyCitationButton({ citation }: { citation: string }) {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(citation).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="tap inline-flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1 text-xs font-medium text-ink/80 transition-colors duration-normal hover:border-white/30 hover:bg-white/10"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? t("evidence.copied") : t("evidence.copyCitation")}
    </button>
  );
}

function AskAboutButton({ excerpt }: { excerpt: string }) {
  const { t } = useLanguage();
  return (
    <button
      type="button"
      onClick={() =>
        window.dispatchEvent(
          new CustomEvent(OPEN_COPILOT_EVENT, {
            detail: { prefill: t("evidence.askPrefill").replace("{excerpt}", excerpt) },
          })
        )
      }
      className="tap inline-flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1 text-xs font-medium text-ink/80 transition-colors duration-normal hover:border-white/30 hover:bg-white/10"
    >
      <BookOpenCheck size={12} />
      {t("evidence.askAbout")}
    </button>
  );
}

/** One piece of evidence, in the shared AI-content skin: a mono source line, a clamped excerpt, the
 * citation as a link when one exists, and the two actions every result offers the same way. */
function EvidenceCard({
  organization,
  year,
  excerpt,
  citation,
  url,
  index,
}: {
  organization: string | null;
  year: number | null;
  excerpt: string;
  citation: string;
  url: string | null;
  index: number;
}) {
  const { t } = useLanguage();
  return (
    <div
      style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
      className="copilot-skin animate-fadeIn rounded-squircle p-4 ring-1 ring-white/10 [animation-fill-mode:both]"
    >
      {(organization || year) && (
        <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          {[organization, year].filter(Boolean).join(" · ")}
        </div>
      )}
      <p className="mt-1.5 line-clamp-4 text-sm leading-relaxed text-ink/90">{excerpt}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="nav-underline tap inline-flex items-center gap-1 text-xs font-semibold text-primary-ink [overflow-wrap:anywhere]"
          >
            {citation}
            <ArrowRight size={11} className="shrink-0 -rotate-45" aria-hidden />
          </a>
        ) : (
          <span className="text-xs font-semibold text-primary-ink [overflow-wrap:anywhere]">{citation}</span>
        )}
        <span className="ml-auto flex gap-1.5">
          <AskAboutButton excerpt={excerpt} />
          <CopyCitationButton citation={citation} />
        </span>
      </div>
    </div>
  );
}

export default function EvidencePage() {
  const { t } = useLanguage();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("");
  const inputRef = useRef<HTMLInputElement>(null);
  const search = useMutation({ mutationFn: (q: string) => api.searchEvidence(q) });

  const { data: categories, isLoading: categoriesLoading } = useQuery({
    queryKey: ["evidence-categories"],
    queryFn: api.evidenceCategories,
  });
  const { data: categoryItems, isLoading: categoryLoading } = useQuery({
    queryKey: ["evidence-category", category],
    queryFn: () => api.evidenceByCategory(category),
    enabled: category !== "",
  });

  useEffect(() => {
    if (categories && categories.length > 0 && category === "") setCategory(categories[0].slug);
  }, [categories, category]);

  useEffect(() => {
    const onSlash = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener("keydown", onSlash);
    return () => window.removeEventListener("keydown", onSlash);
  }, []);

  const submit = () => query.trim() && search.mutate(query.trim());
  const showingSearch = search.data !== undefined;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow={t("patients.eyebrow")}
        title={t("nav.evidence")}
        subtitle={t("evidence.subtitle")}
      />

      <div className="copilot-skin rounded-squircle p-2 ring-1 ring-white/15">
        <div className="flex items-center gap-2 px-3 py-2.5">
          <BookOpenCheck size={16} className="shrink-0 text-primary-ink" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={t("evidence.searchPlaceholder")}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-muted focus-visible:!outline-none"
          />
          <button
            onClick={submit}
            disabled={search.isPending || !query.trim()}
            className="tap flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/15 text-primary-ink transition-colors disabled:cursor-not-allowed disabled:bg-surface/60 disabled:text-muted"
            aria-label={t("evidence.search")}
          >
            <ArrowRight size={15} />
          </button>
        </div>
        {!showingSearch && (
          <div className="flex flex-wrap gap-1.5 px-2 pb-1">
            {EXAMPLE_KEYS.map((key) => (
              <button
                key={key}
                onClick={() => {
                  setQuery(t(key));
                  search.mutate(t(key));
                }}
                className="tap rounded-full border border-white/10 px-2.5 py-1 text-xs text-muted transition-colors duration-normal hover:border-white/25 hover:text-ink"
              >
                {t(key)}
              </button>
            ))}
          </div>
        )}
      </div>

      {showingSearch ? (
        <div className="space-y-3">
          <button
            onClick={() => {
              search.reset();
              setQuery("");
            }}
            className="nav-underline tap text-xs font-medium text-muted hover:text-ink"
          >
            {t("evidence.backToCategories")}
          </button>
          {search.data!.results.length === 0 ? (
            <p className="text-sm text-muted">{t("evidence.noResults")}</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {search.data!.results.map((r, i) => (
                <EvidenceCard
                  key={i}
                  index={i}
                  organization={null}
                  year={null}
                  excerpt={r.content}
                  citation={r.citation}
                  url={r.url}
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {categoriesLoading ? (
            <p className="text-sm text-muted">{t("evidence.loadingCategories")}</p>
          ) : categories && categories.length > 0 ? (
            <>
              <FilterTabs
                label={t("evidence.browseByCategory")}
                value={category}
                onChange={setCategory}
                tabs={categories.map((c) => ({ value: c.slug, label: c.label, count: c.count }))}
              />
              {categoryLoading ? (
                <p className="text-sm text-muted">{t("common.loading")}</p>
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {categoryItems?.map((item: EvidenceItem, i) => (
                    <EvidenceCard
                      key={item.id}
                      index={i}
                      organization={item.organization}
                      year={item.year}
                      excerpt={item.excerpt || item.title}
                      citation={item.citation}
                      url={item.url}
                    />
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">{t("evidence.noResults")}</p>
          )}
        </div>
      )}
    </div>
  );
}
