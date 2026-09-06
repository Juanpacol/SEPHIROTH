"use client";

/** Loading placeholders.
 *
 * Every list in this app currently renders the literal string "Loading…" while
 * it waits, which makes the page jump when content arrives and tells the reader
 * nothing about what is coming. A skeleton reserves the real shape.
 *
 * `aria-hidden`, and the container carries `aria-busy`: a screen reader should
 * hear "loading", not a description of grey rectangles. */

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-xl bg-line/50 ${className}`} />;
}

/** The shape of a list of cards/rows — the task inbox, alerts, results. */
export function SkeletonRows({ rows = 4, label }: { rows?: number; label: string }) {
  return (
    <div aria-busy="true" aria-label={label} className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="card flex items-center gap-3">
          <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="h-6 w-16 shrink-0" />
        </div>
      ))}
    </div>
  );
}

export default Skeleton;
