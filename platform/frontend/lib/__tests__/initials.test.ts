import { describe, expect, it } from "vitest";
import { initialsOf } from "@/lib/initials";

describe("initialsOf", () => {
  it("takes the first and the last name, never the whole name", () => {
    expect(initialsOf("María Fernanda Restrepo Villegas")).toBe("MV");
    expect(initialsOf("Lucía Gómez")).toBe("LG");
  });

  it("drops a title and copes with one name or none", () => {
    expect(initialsOf("Dr. Ana Ruiz")).toBe("AR");
    expect(initialsOf("Madonna")).toBe("M");
    expect(initialsOf("  ")).toBe("?");
  });
});
