import { describe, expect, it } from "vitest";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";

/** The landing page may only describe what the product does. SPEC-029 removed the
 * Coordinator and Laboratory agents and the multi-agent fan-out: one specialist
 * answers each question. These read the copy, so a sentence that brings any of
 * that back fails here instead of reaching a visitor. */
const DICTIONARIES = { en: EN as Record<string, string>, es: ES as Record<string, string> };
const MARKETING = (dict: Record<string, string>) =>
  Object.entries(dict).filter(([key]) => key.startsWith("marketing."));

describe("landing copy describes the agents that exist", () => {
  for (const [lang, dict] of Object.entries(DICTIONARIES)) {
    it(`${lang}: has no key for the removed Coordinator or Laboratory agents`, () => {
      const stale = Object.keys(dict).filter((key) =>
        /^marketing\.(agentName|agentsSection)\.(coordinator|laboratory)/.test(key),
      );
      expect(stale).toEqual([]);
    });

    it(`${lang}: never says a question fans out, is merged, or needs four or six parts`, () => {
      const offenders = MARKETING(dict)
        .filter(([, value]) =>
          /coordinator|coordinador|fans? out|se reparte|all four|los cuatro|four lookups|cuatro búsquedas|six steps|seis pasos/i.test(
            value,
          ),
        )
        .map(([key]) => key);
      expect(offenders).toEqual([]);
    });

    it(`${lang}: names the three agents by what they do`, () => {
      const names = ["radiology", "drugSafety", "evidence"].map((k) => dict[`marketing.agentName.${k}`]);
      expect(names).toEqual(
        lang === "en"
          ? ["Image Analysis", "Medication Interactions", "Guidelines & Literature"]
          : ["Análisis de imagen", "Interacciones medicamentosas", "Guías y literatura"],
      );
    });
  }
});
