import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { DEMO_STUDIES } from "@/lib/imaging-demo";

/** The landing demo's analyses are a copy of the file the Imaging page serves. The
 * public page cannot reach the API, so the copy has to be kept honest by a test. */
const root = path.join(__dirname, "../..");
const source = path.join(root, "../api/static/imaging-demo/analyses.json");

describe("landing imaging demo", () => {
  it("shows the four studies, each with an image that exists", () => {
    expect(DEMO_STUDIES.map((s) => s.modality)).toEqual(["XRAY", "CT", "MRI", "ULTRASOUND"]);
    for (const study of DEMO_STUDIES) {
      expect(existsSync(path.join(root, "public", study.image)), study.image).toBe(true);
    }
  });

  it("each analysis is a complete answer, not a cut-off one", () => {
    for (const study of DEMO_STUDIES) {
      expect(study.description.split(/\s+/).length, study.id).toBeGreaterThanOrEqual(40);
      expect(study.description.trim(), study.id).toMatch(/[.)]$/);
    }
  });

  it.skipIf(!existsSync(source))("is the same text the app serves, word for word", () => {
    const served = JSON.parse(readFileSync(source, "utf8")) as {
      file: string;
      modality: string;
      region: string;
      model: string;
      description: string;
    }[];
    expect(DEMO_STUDIES).toEqual(
      served.map((a) => ({
        id: a.file.replace(/\.webp$/, ""),
        image: `/landing/analysis/${a.file}`,
        modality: a.modality,
        region: a.region,
        model: a.model,
        description: a.description,
      })),
    );
  });
});
