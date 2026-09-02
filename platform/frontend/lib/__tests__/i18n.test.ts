import { describe, expect, it } from "vitest";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";

describe("i18n dictionary parity", () => {
  it("has every English key present in Spanish", () => {
    const missing = Object.keys(EN).filter((key) => !(key in ES));
    expect(missing, `keys missing from dictionaries.es.ts: ${missing.join(", ")}`).toEqual([]);
  });

  it("has every Spanish key present in English", () => {
    const missing = Object.keys(ES).filter((key) => !(key in EN));
    expect(missing, `keys missing from dictionaries.en.ts: ${missing.join(", ")}`).toEqual([]);
  });
});
