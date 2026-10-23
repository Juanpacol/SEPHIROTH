/** An imaging event's `detail` is stored as "[image_path:…] [model:…] description…": the backend reads
 * those two tags back (`routers/medical.py`), so the storage stays, and the screen is what changes. Here the
 * tags come off the text and travel separately, and a long description is cut to its opening sentence. */
const TAGS = /^\s*\[image_path:([^\]]+)\]\s*(?:\[model:([^\]]+)\]\s*)?([\s\S]*)$/;

export interface ParsedDetail {
  imagePath: string | null;
  model: string | null;
  text: string;
}

export function parseEventDetail(detail: string): ParsedDetail {
  const match = TAGS.exec(detail ?? "");
  if (!match) return { imagePath: null, model: null, text: (detail ?? "").trim() };
  return { imagePath: match[1], model: match[2] ?? null, text: match[3].trim() };
}

/** The opening sentence, or the first `max` characters cut at a word, with an ellipsis when something is left. */
export function summarize(text: string, max = 160): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const sentence = /^(.+?[.!?])(\s|$)/.exec(flat)?.[1] ?? flat;
  if (sentence.length <= max) return sentence.length < flat.length ? `${sentence} …` : sentence;
  const cut = flat.slice(0, max);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), 40))} …`;
}

/** "2026-08-14T09:00:00" → "14 Aug 2026"; anything that is not a date is shown as it came. */
export function formatEventDate(raw: string, lang: string): string {
  // A bare date ("2026-05-01") would be read as midnight UTC and show as the day before west of Greenwich.
  const bare = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  const d = bare ? new Date(Number(bare[1]), Number(bare[2]) - 1, Number(bare[3])) : new Date(raw);
  return Number.isNaN(d.getTime())
    ? raw
    : d.toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" });
}
