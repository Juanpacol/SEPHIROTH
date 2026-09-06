"use client";

/** One list, two shapes: a real `<table>` from `md:` up, a stack of cards
 * below it.
 *
 * Deliberately one component rather than a `<Table>` / `<CardList>` pair. The
 * pair is the obvious factoring and it is the wrong one: two components mean
 * two places to add a column, and the mobile one silently falls behind because
 * nobody develops on a phone. Here a column is declared once and both shapes
 * are generated from it, so they cannot drift.
 *
 * Both shapes render at every width and CSS picks — no `useMediaQuery`, no
 * layout shift on hydration, no client/server mismatch. The duplicate DOM is
 * cheap at inbox sizes and is what buys the guarantee above.
 *
 * `primary: true` marks the columns that survive on a phone card; everything
 * else becomes a labelled line under them. If no column is marked, the first is
 * treated as primary — a wrong-looking card is better than an empty one. */

import { Fragment } from "react";
import { SkeletonRows } from "./skeleton";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  /** Shown as the card's headline on a phone rather than as a labelled line. */
  primary?: boolean;
  /** Dropped entirely from the card shape — noise a phone has no room for. */
  desktopOnly?: boolean;
  className?: string;
}

export default function DataList<T>({
  items,
  columns,
  rowKey,
  onRowHref,
  isLoading = false,
  loadingLabel,
  emptyLabel,
  caption,
}: {
  items: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** Makes the whole card tappable on a phone, where a small link inside a row
   * is a poor target. The table shape keeps whatever links the cells render. */
  onRowHref?: (row: T) => string;
  isLoading?: boolean;
  loadingLabel: string;
  emptyLabel: string;
  caption: string;
}) {
  if (isLoading) return <SkeletonRows label={loadingLabel} />;

  if (items.length === 0) {
    return (
      <div className="card text-sm text-muted" role="status">
        {emptyLabel}
      </div>
    );
  }

  const primary = columns.filter((c) => c.primary);
  const headline = primary.length > 0 ? primary : columns.slice(0, 1);
  const secondary = columns.filter((c) => !headline.includes(c) && !c.desktopOnly);

  return (
    <>
      {/* Cards — phones. */}
      <ul className="flex flex-col gap-2 md:hidden">
        {items.map((row) => {
          const href = onRowHref?.(row);
          const body = (
            <>
              {headline.map((col) => (
                <div key={col.key} className="font-semibold text-ink">
                  {col.render(row)}
                </div>
              ))}
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
                {secondary.map((col) => (
                  <Fragment key={col.key}>
                    <dt className="text-xs uppercase tracking-wider text-muted">{col.header}</dt>
                    <dd className="text-right text-ink/80">{col.render(row)}</dd>
                  </Fragment>
                ))}
              </dl>
            </>
          );

          return (
            <li key={rowKey(row)} className="card">
              {href ? (
                <a href={href} className="block">
                  {body}
                </a>
              ) : (
                body
              )}
            </li>
          );
        })}
      </ul>

      {/* Table — tablet and up. */}
      <div className="card hidden overflow-x-auto !p-0 md:block">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-line/60 text-left text-xs uppercase tracking-wider text-muted">
              {columns.map((col) => (
                <th key={col.key} scope="col" className="px-5 py-3.5">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={rowKey(row)} className="border-b border-line/40 last:border-0 hover:bg-surface/60">
                {columns.map((col) => (
                  <td key={col.key} className={`px-5 py-3.5 ${col.className ?? ""}`}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
