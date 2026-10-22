import { describe, expect, it } from "vitest";
import { agentLabel } from "@/lib/agents";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";

const en = (key: string) => (EN as Record<string, string>)[key] ?? key;
const es = (key: string) => (ES as Record<string, string>)[key] ?? key;

describe("agentLabel", () => {
  it("names each agent by what it does, in the reader's language", () => {
    expect(agentLabel("radiology", en)).toBe("Image Analysis");
    expect(agentLabel("drug-safety", en)).toBe("Medication Interactions");
    expect(agentLabel("evidence", en)).toBe("Guidelines & Literature");
    expect(agentLabel("radiology", es)).toBe("Análisis de imagen");
    expect(agentLabel("drug-safety", es)).toBe("Interacciones medicamentosas");
    expect(agentLabel("evidence", es)).toBe("Guías y literatura");
  });

  it("takes both spellings of drug safety that appear on the wire", () => {
    expect(agentLabel("drug_safety", en)).toBe("Medication Interactions");
  });

  it("shows an id it does not know exactly as it came", () => {
    expect(agentLabel("coordinator", en)).toBe("coordinator");
    expect(agentLabel("", en)).toBe("");
  });
});
