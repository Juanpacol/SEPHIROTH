"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpenCheck, ChevronRight, Search } from "lucide-react";
import { api, type EvidenceItem } from "@/lib/api";

function CategoryGroup({ slug, label, count }: { slug: string; label: string; count: number }) {
  const [open, setOpen] = useState(false);
  const { data: items, isLoading } = useQuery({
    queryKey: ["evidence-category", slug],
    queryFn: () => api.evidenceByCategory(slug),
    enabled: open,
  });

  return (
    <div className="card !p-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 font-semibold">
          <ChevronRight size={15} className={`text-muted transition-transform ${open ? "rotate-90" : ""}`} />
          {label}
        </span>
        <span className="rounded-full bg-primary-soft px-2 py-0.5 text-xs font-semibold text-primary">
          {count}
        </span>
      </button>

      {open && (
        <div className="border-t border-line/60 px-4 pb-4 pt-1">
          {isLoading && <p className="py-2 text-sm text-muted">Loading…</p>}
          <ul className="divide-y divide-line/50">
            {items?.map((item) => <EvidenceRow key={item.id} item={item} />)}
          </ul>
        </div>
      )}
    </div>
  );
}

function EvidenceRow({ item }: { item: EvidenceItem }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="py-3">
      <button onClick={() => setExpanded((e) => !e)} className="w-full text-left">
        <p className="text-sm font-semibold text-ink">{item.title}</p>
        <p className="text-xs text-muted">
          {item.organization}
          {item.year ? ` · ${item.year}` : ""}
        </p>
      </button>
      {expanded && (
        <div className="mt-2 rounded-xl bg-surface p-3">
          <p className="text-sm leading-relaxed">{item.excerpt}</p>
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block text-xs font-semibold text-primary underline underline-offset-2"
            >
              {item.citation} — view source ↗
            </a>
          ) : (
            <p className="mt-2 text-xs font-semibold text-primary">{item.citation}</p>
          )}
        </div>
      )}
    </li>
  );
}

export default function EvidencePage() {
  const [query, setQuery] = useState("");
  const search = useMutation({ mutationFn: (q: string) => api.searchEvidence(q) });
  const { data: categories, isLoading: categoriesLoading } = useQuery({
    queryKey: ["evidence-categories"],
    queryFn: api.evidenceCategories,
  });

  const submit = () => query.trim() && search.mutate(query);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">Evidence Library</h1>
        <p className="text-sm text-muted">
          Browse indexed clinical guidelines by category, or search a specific question — every
          result carries its citation.
        </p>
      </div>

      <div className="card flex items-center gap-2 !p-3">
        <Search size={16} className="ml-1 text-muted" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="e.g. blood pressure target for adults with hypertension"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none"
        />
        <button
          onClick={submit}
          disabled={search.isPending}
          className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          Search
        </button>
      </div>

      {search.data ? (
        <div className="space-y-3">
          {search.data.results.map((result, i) => (
            <div key={i} className="card">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 rounded-lg bg-primary-soft p-2 text-primary">
                  <BookOpenCheck size={16} />
                </span>
                <div>
                  <p className="text-sm leading-relaxed">{result.content}</p>
                  {result.url ? (
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-block text-xs font-semibold text-primary underline underline-offset-2"
                    >
                      {result.citation} — view source ↗
                    </a>
                  ) : (
                    <p className="mt-2 text-xs font-semibold text-primary">{result.citation}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
          {search.data.results.length === 0 && (
            <div className="card text-sm text-muted">No matching guidelines found.</div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
            Browse by category
          </h2>
          {categoriesLoading && <p className="text-sm text-muted">Loading categories…</p>}
          {categories?.map((c) => <CategoryGroup key={c.slug} {...c} />)}
        </div>
      )}
    </div>
  );
}
