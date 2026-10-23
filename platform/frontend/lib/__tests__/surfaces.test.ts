import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

/** One guard on the shadow tokens. The rest of what used to be pinned here (the hairline, the
 * layers, the radii) described how the surfaces looked at the time, and failed on any change of
 * look without protecting anyone. */
const extend = config.theme?.extend as Record<string, Record<string, string>>;

describe("shadows", () => {
  it("never shares a name with a colour: Tailwind would make `shadow-<colour>` and the colour's rule would win", () => {
    const colours = Object.keys((extend as unknown as { colors: Record<string, unknown> }).colors ?? {});
    for (const name of Object.keys(extend.boxShadow)) expect(colours, name).not.toContain(name);
  });
});
