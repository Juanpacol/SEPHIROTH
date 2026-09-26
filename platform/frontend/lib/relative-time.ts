import type { Lang } from "@/lib/language";

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

const HAS_ZONE = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

/** "hace 5 min" / "5 min. ago" (or "en 2 días" for a future due date).
 * Backend datetimes are naive UTC, so a zone-less string gets `Z` appended —
 * same convention as `components/schedule/time.ts`. */
export function relativeTime(iso: string | null | undefined, lang: Lang, now: Date = new Date()): string {
  if (!iso) return "";
  const date = new Date(HAS_ZONE.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return "";
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const format = new Intl.RelativeTimeFormat(lang, { numeric: "auto", style: "short" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return format.format(0, "second");
}
