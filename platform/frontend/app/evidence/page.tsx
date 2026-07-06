"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { BookOpenCheck, Search } from "lucide-react";
import { api } from "@/lib/api";

export default function EvidencePage() {
  const [query, setQuery] = useState("");
  const search = useMutation({ mutationFn: (q: string) => api.searchEvidence(q) });

  const submit = () => query.trim() && search.mutate(query);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">Evidence Library</h1>
        <p className="text-sm text-muted">
          Search indexed clinical guidelines — every result carries its citation
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

      {search.data?.results.map((result, i) => (
        <div key={i} className="card">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 rounded-lg bg-primary-soft p-2 text-primary">
              <BookOpenCheck size={16} />
            </span>
            <div>
              <p className="text-sm leading-relaxed">{result.content}</p>
              <p className="mt-2 text-xs font-semibold text-primary">{result.citation}</p>
            </div>
          </div>
        </div>
      ))}
      {search.data && search.data.results.length === 0 && (
        <div className="card text-sm text-muted">No matching guidelines found.</div>
      )}
    </div>
  );
}
