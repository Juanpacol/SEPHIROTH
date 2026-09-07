import { beforeEach, describe, expect, it } from "vitest";
import { AUTH_GATE_SCRIPT } from "@/lib/auth-gate";

/** `AUTH_GATE_SCRIPT` is a plain string meant to run in a `<head>` inline
 * script tag before hydration — executing it via `new Function` in this
 * jsdom environment exercises the exact same code path without needing a
 * real browser. */
function runGateScript() {
  // eslint-disable-next-line no-new-func
  new Function(AUTH_GATE_SCRIPT)();
}

describe("AUTH_GATE_SCRIPT", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-auth-redirect");
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, pathname: "/", replace: () => {} },
    });
  });

  it("does nothing when not on the landing page", () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, pathname: "/dashboard" },
    });
    localStorage.setItem("cac_token", "tok");

    expect(() => runGateScript()).not.toThrow();
    expect(document.documentElement.hasAttribute("data-auth-redirect")).toBe(false);
  });

  it("does nothing when logged out", () => {
    expect(() => runGateScript()).not.toThrow();
    expect(document.documentElement.hasAttribute("data-auth-redirect")).toBe(false);
  });

  it("redirects a logged-in clinician to /dashboard", () => {
    localStorage.setItem("cac_token", "tok");
    localStorage.setItem("cac_user", JSON.stringify({ role: "clinician" }));
    let redirectedTo = "";
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...window.location,
        pathname: "/",
        replace: (url: string) => {
          redirectedTo = url;
        },
      },
    });

    runGateScript();

    expect(redirectedTo).toBe("/dashboard");
    expect(document.documentElement.hasAttribute("data-auth-redirect")).toBe(true);
  });

  it("redirects a logged-in patient to /portal", () => {
    localStorage.setItem("cac_token", "tok");
    localStorage.setItem("cac_user", JSON.stringify({ role: "patient" }));
    let redirectedTo = "";
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...window.location,
        pathname: "/",
        replace: (url: string) => {
          redirectedTo = url;
        },
      },
    });

    runGateScript();

    expect(redirectedTo).toBe("/portal");
  });

  it("swallows a corrupt cac_user value instead of throwing", () => {
    localStorage.setItem("cac_token", "tok");
    localStorage.setItem("cac_user", "{not-json");

    expect(() => runGateScript()).not.toThrow();
  });
});
