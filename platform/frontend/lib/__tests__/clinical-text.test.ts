import { describe, expect, it } from "vitest";
import { friendlyTestName } from "@/lib/clinical-text";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";

const tFor = (dict: Record<string, string>) => (key: string) => dict[key] ?? key;
const es = tFor(ES);
const en = tFor(EN);

describe("friendlyTestName", () => {
  it("names blood pressure clinically instead of as a raw key", () => {
    expect(friendlyTestName("bp_systolic", es)).toBe("Presión sistólica");
    expect(friendlyTestName("bp_diastolic", es)).toBe("Presión diastólica");
    expect(friendlyTestName("bp_systolic", en)).toBe("Systolic BP");
    expect(friendlyTestName("bp_diastolic", en)).toBe("Diastolic BP");
  });

  it("still resolves Spanish and short-form aliases", () => {
    expect(friendlyTestName("potasio", es)).toBe("Potasio");
    expect(friendlyTestName("K", en)).toBe("Potassium");
  });

  it("humanizes an unmapped key rather than printing underscores", () => {
    expect(friendlyTestName("some_new_test", es)).toBe("Some new test");
    expect(friendlyTestName("troponin", en)).toBe("Troponin");
  });

  it("renders nothing for a missing name", () => {
    expect(friendlyTestName(undefined, es)).toBe("");
  });
});
