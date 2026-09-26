import { describe, expect, it } from "vitest";
import { relativeTime } from "@/lib/relative-time";

const NOW = new Date("2026-09-26T15:00:00Z");

describe("relativeTime", () => {
  it("reads naive backend timestamps as UTC", () => {
    expect(relativeTime("2026-09-26T14:55:00", "es", NOW)).toBe("hace 5 min");
    expect(relativeTime("2026-09-26T14:55:00Z", "es", NOW)).toBe("hace 5 min");
  });

  it("scales to the largest sensible unit, in the active language", () => {
    expect(relativeTime("2026-09-26T12:00:00", "es", NOW)).toBe("hace 3 h");
    expect(relativeTime("2026-09-26T12:00:00", "en", NOW)).toBe("3 hr. ago");
    expect(relativeTime("2026-09-25T15:00:00", "es", NOW)).toBe("ayer");
    expect(relativeTime("2026-09-14T15:00:00", "en", NOW)).toBe("12 days ago");
  });

  it("says just now for the current minute", () => {
    expect(relativeTime("2026-09-26T14:59:40", "es", NOW)).toBe("ahora");
  });

  it("handles a future date", () => {
    expect(relativeTime("2026-09-28T15:00:00", "en", NOW)).toBe("in 2 days");
  });

  it("renders nothing for a missing or unparseable value", () => {
    expect(relativeTime(null, "es", NOW)).toBe("");
    expect(relativeTime("not a date", "es", NOW)).toBe("");
  });
});
