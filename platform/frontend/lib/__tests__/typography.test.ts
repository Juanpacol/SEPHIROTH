import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

/** The type system (AB#40): free fonts hosted in the repo with their licences, and a label that
 * stays readable. Reads the sources as text so a trial font or a Google fetch at build time fails
 * here. (The named scale and the label style used to be pinned too: they described a look.) */
const root = path.join(__dirname, "../..");
const read = (rel: string) => readFileSync(path.join(root, rel), "utf8");

function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(path.join(root, dir))) {
    const rel = path.join(dir, name);
    if (name === "node_modules" || name === ".next" || name === "__tests__") continue;
    if (statSync(path.join(root, rel)).isDirectory()) sources(rel, out);
    else if (/\.(tsx?|css)$/.test(name)) out.push(rel);
  }
  return out;
}

describe("fonts", () => {
  const fonts = [
    ["Manrope-latin-wght.woff2", "OFL.txt"],
    ["Antonio-latin-wght.woff2", "OFL-Antonio.txt"],
    ["JetBrainsMono-latin-wght.woff2", "OFL-JetBrainsMono.txt"],
  ];

  it.each(fonts)(
    "%s is hosted in the repo, is a real woff2, and travels with its licence (%s)",
    (font, licence) => {
      const file = path.join(root, "app/fonts", font);
      expect(existsSync(file)).toBe(true);
      expect(readFileSync(file).subarray(0, 4).toString("ascii")).toBe("wOF2");
      expect(statSync(file).size).toBeLessThan(80_000);
      expect(read(`app/fonts/${licence}`)).toMatch(/SIL Open Font License, Version 1\.1/);
    },
  );

  it("documents the source and licence of each font", () => {
    const readme = read("app/fonts/README.md");
    for (const [font] of fonts) expect(readme).toContain(font);
    expect(readme).toMatch(/@fontsource-variable\/antonio/);
    expect(readme).toMatch(/@fontsource-variable\/jetbrains-mono/);
  });

  it("loads them from the repo at build time, never from Google", () => {
    const layout = read("app/layout.tsx");
    expect(layout).toContain('from "next/font/local"');
    expect(layout).not.toMatch(/from "next\/font\/google"/);
    expect(layout).toContain('variable: "--font-display"');
    expect(layout).toContain('variable: "--font-mono"');
  });

  it("uses no trial or commercial font anywhere in the source", () => {
    const offenders = sources("app")
      .concat(sources("components"), sources("lib"))
      .concat(["tailwind.config.ts"])
      .filter((f) => /Rules (Gothic|Variable|Extended|Condensed)|Aeonik|Pro TRIAL/i.test(read(f)));
    expect(offenders).toEqual([]);
  });
});

describe("scale", () => {
  const theme = config.theme?.extend as Record<string, Record<string, unknown>>;

  it("keeps the label at 11 px or more", () => {
    const [size] = theme.fontSize.label as [string];
    expect(parseFloat(size) * 16).toBeGreaterThanOrEqual(11);
  });
});
