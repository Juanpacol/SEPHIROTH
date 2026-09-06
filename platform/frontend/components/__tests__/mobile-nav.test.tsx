/** `MobileNav` — the bottom bar and its overflow drawer.
 *
 * Below `md` the app had no navigation at all: the sidebar is `hidden md:flex`
 * with nothing in its place, so a clinician on a phone could reach exactly the
 * page they landed on. The test that matters most here is the last one: every
 * destination the sidebar offers must be reachable on a phone, either from the
 * bar or from the drawer. That is the property sharing `lib/nav.ts` buys, and
 * the one that silently rots if the two lists are ever maintained separately.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MobileNav from "@/components/mobile-nav";
import { LanguageProvider } from "@/lib/language";
import { CLINICIAN_NAV, PATIENT_NAV, flatNav } from "@/lib/nav";

const pathname = vi.fn(() => "/patients");
const push = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => pathname(),
  useRouter: () => ({ push }),
}));

const user = vi.fn<() => { name: string; role: string } | null>(() => ({
  name: "Dra. Ruiz",
  role: "clinician",
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { ...actual.api, badges: vi.fn().mockResolvedValue({}) } };
});

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return { ...actual, useUser: () => user(), clearAuth: vi.fn() };
});

function renderNav() {
  // MobileNav reads the shared badge counters, so it needs a query client.
  // `retry: false` keeps a failing fetch from retrying past the test.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <MobileNav />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe("MobileNav", () => {
  beforeEach(() => {
    pathname.mockReturnValue("/patients");
    user.mockReturnValue({ name: "Dra. Ruiz", role: "clinician" });
  });

  it("puts the four promoted destinations in the bar, plus a More trigger", () => {
    renderNav();
    const bar = screen.getByRole("navigation");

    const promoted = flatNav(CLINICIAN_NAV).filter((i) => i.mobile);
    expect(promoted).toHaveLength(4);
    for (const item of promoted) {
      expect(within(bar).getByRole("link", { name: new RegExp(item.id, "i") })).toBeTruthy();
    }
    expect(within(bar).getByRole("button", { name: /more/i })).toBeInTheDocument();
  });

  it("AC-017-07 — marks the current destination for assistive tech, not just visually", () => {
    renderNav();
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveAttribute("href", "/patients");
  });

  it("AC-017-07 — resolves a nested route to its parent destination", () => {
    pathname.mockReturnValue("/patients/P001");
    renderNav();
    expect(screen.getByRole("link", { current: "page" })).toHaveAttribute("href", "/patients");
  });

  it("AC-017-08 — opens the drawer with the overflow destinations and closes it on Escape", () => {
    renderNav();
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /more/i }));
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByRole("link", { name: /imaging/i })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("AC-017-06 — reaches every sidebar destination from either the bar or the drawer", () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: /more/i }));

    const hrefs = new Set(
      screen.getAllByRole("link").map((el) => el.getAttribute("href")),
    );
    for (const item of flatNav(CLINICIAN_NAV)) {
      expect(hrefs).toContain(item.href);
    }
  });

  it("shows the patient portal's destinations, with no overflow drawer", () => {
    user.mockReturnValue({ name: "Ana", role: "patient" });
    pathname.mockReturnValue("/portal");
    renderNav();

    const bar = screen.getByRole("navigation");
    expect(within(bar).getAllByRole("link")).toHaveLength(flatNav(PATIENT_NAV).length);
    // All three fit, so there is nothing to hide behind "More".
    expect(within(bar).queryByRole("button", { name: /more/i })).toBeNull();
  });
});
