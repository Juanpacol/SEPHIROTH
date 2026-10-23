import { describe, expect, it } from "vitest";
import { formatEventDate, parseEventDetail, summarize } from "@/lib/timeline-detail";

describe("parseEventDetail", () => {
  it("takes the storage tags off an imaging description", () => {
    const parsed = parseEventDetail(
      "[image_path:demo:ct-brain.webp] [model:gemini-flash-latest] This image shows a CT."
    );
    expect(parsed).toEqual({
      imagePath: "demo:ct-brain.webp",
      model: "gemini-flash-latest",
      text: "This image shows a CT.",
    });
  });

  it("copes with a missing model tag and with plain text", () => {
    expect(parseEventDetail("[image_path:a.png] Seen.")).toEqual({
      imagePath: "a.png",
      model: null,
      text: "Seen.",
    });
    expect(parseEventDetail("Stable on therapy")).toEqual({
      imagePath: null,
      model: null,
      text: "Stable on therapy",
    });
  });
});

describe("summarize", () => {
  it("keeps a short text whole", () => {
    expect(summarize("Stable on optimized therapy")).toBe("Stable on optimized therapy");
  });

  it("keeps the opening sentence and says there is more", () => {
    expect(summarize("A CT of the head. It shows air. More follows.")).toBe("A CT of the head. …");
  });

  it("cuts a long sentence at a word", () => {
    const long = `${"word ".repeat(60)}end.`;
    const out = summarize(long, 50);
    expect(out.endsWith("…")).toBe(true);
    expect(out.length).toBeLessThanOrEqual(54);
  });
});

describe("formatEventDate", () => {
  it("writes a bare date as that day, whatever the time zone", () => {
    expect(formatEventDate("2026-05-01", "en")).toBe("May 1, 2026");
  });

  it("writes a date-time as its day and leaves anything else as it came", () => {
    expect(formatEventDate("2026-08-14T09:00:00", "en")).toBe("Aug 14, 2026");
    expect(formatEventDate("last spring", "en")).toBe("last spring");
  });
});
