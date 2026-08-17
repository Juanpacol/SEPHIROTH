"use client";

/** The landing page's centerpiece: click through (or auto-play) the five
 * stages of a real consultation. Autoplay is off by default and only
 * starts on explicit click, per the accessibility guidance for
 * auto-advancing content — it also pauses on hover/focus. Under
 * `prefers-reduced-motion: reduce`, transitions collapse via the
 * `motion-reduce:` utility and the "thinking" dots render as static text
 * instead of animating. */

import { useEffect, useRef, useState } from "react";
import { Play, Pause } from "lucide-react";
import AgentBadge from "@/components/agent-badge";
import {
  WALKTHROUGH_STAGES,
  SAMPLE_QUESTION,
  SAMPLE_SPECIALISTS,
  SAMPLE_DRAFT,
  SAMPLE_GUARDED,
  SAMPLE_CLAIMS,
  CLAIM_LEGEND,
} from "@/lib/landing-content";

export default function ConsultationWalkthrough() {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!playing) return;
    intervalRef.current = setInterval(() => {
      setIndex((i) => (i + 1) % WALKTHROUGH_STAGES.length);
    }, 2200);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing]);

  const stage = WALKTHROUGH_STAGES[index];

  return (
    <div
      className="card"
      onMouseEnter={() => setPlaying(false)}
      onFocus={() => setPlaying(false)}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Consultation stages"
          className="flex flex-wrap items-center gap-1.5"
        >
          {WALKTHROUGH_STAGES.map((s, i) => (
            <button
              key={s.id}
              role="tab"
              aria-selected={i === index}
              onClick={() => setIndex(i)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors motion-reduce:transition-none ${
                i === index ? "bg-primary text-white" : "bg-primary-soft text-primary hover:brightness-95"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause" : "Run it"}
          className="btn-secondary py-1.5 text-xs"
        >
          {playing ? <Pause size={13} /> : <Play size={13} />}
          {playing ? "Pause" : "Run it"}
        </button>
      </div>

      <div
        role="tabpanel"
        aria-live="polite"
        className="min-h-[22rem] animate-fadeIn motion-reduce:animate-none"
        key={stage.id}
      >
        {stage.render === "routing" && (
          <div>
            <p className="mb-4 text-sm text-muted">A clinician asks:</p>
            <p className="card border border-line/70 text-sm font-medium">{SAMPLE_QUESTION}</p>
            <p className="mt-4 text-sm text-muted">
              The router tags this question and selects the specialists it needs — not every
              consultation runs all four.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {["Evidence", "Laboratory", "Radiology", "Drug Safety"].map((name) => (
                <span
                  key={name}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                    ["Evidence", "Laboratory"].includes(name)
                      ? "bg-primary text-white"
                      : "bg-surface text-muted line-through"
                  }`}
                >
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}

        {stage.render === "specialists" && (
          <div className="space-y-3">
            <p className="mb-2 text-sm text-muted">Each selected specialist runs independently:</p>
            {SAMPLE_SPECIALISTS.map((s) => (
              <div key={s.name} className="card border border-line/70">
                <div className="mb-1 flex items-center gap-2">
                  <AgentBadge name={s.name} />
                </div>
                <p className="text-sm">{s.finding}</p>
              </div>
            ))}
          </div>
        )}

        {stage.render === "synthesize" && (
          <div>
            <p className="mb-2 text-sm text-muted">The Coordinator merges the specialists' findings:</p>
            <div className="card border border-primary/30 ai-ring">
              <div className="mb-2">
                <AgentBadge name="Coordinator (draft)" />
              </div>
              <p className="text-sm">{SAMPLE_DRAFT}</p>
            </div>
          </div>
        )}

        {stage.render === "guard" && (
          <div>
            <p className="mb-2 text-sm text-muted">
              Citation Guard checks every bracketed citation against what the tools actually
              returned:
            </p>
            <div className="card border border-line/70">
              <p className="text-sm">
                Target A1C is &lt;7% [ADA Standards of Care, 2024]{" "}
                <span className="text-danger line-through opacity-60">
                  [UpToDate Diabetes Review, 2023]
                </span>{" "}
                → <span className="font-semibold text-danger">[unverified — removed]</span>. Current
                value (8.1%) is above goal.
              </p>
            </div>
            <p className="mt-2 text-xs text-muted">
              Result: <span className="font-mono">{SAMPLE_GUARDED}</span>
            </p>
          </div>
        )}

        {stage.render === "verify" && (
          <div>
            <p className="mb-2 text-sm text-muted">
              Every remaining claim is classified into one of 5 states before the answer ships:
            </p>
            <div className="mb-3 flex flex-wrap gap-3 text-xs">
              {CLAIM_LEGEND.map((l) => (
                <span key={l.state} className={`font-semibold ${l.color}`}>
                  ● {l.label}
                </span>
              ))}
            </div>
            <div className="space-y-2">
              {SAMPLE_CLAIMS.map((c) => (
                <div key={c.text} className="card border border-line/70 py-2.5">
                  <p className="text-sm">{c.text}</p>
                  <p className="mt-1 text-xs text-muted">{c.action}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
