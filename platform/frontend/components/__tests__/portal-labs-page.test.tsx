import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PortalLabsPage from "@/app/portal/labs/page";
import { api, type PortalLab } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const lab = (over: Partial<PortalLab> = {}): PortalLab => ({
  share_id: "s-1",
  test_name: "potassium",
  value: 6.4,
  unit: "mmol/L",
  taken_at: "2026-10-10T08:00:00",
  reference_low: 3.5,
  reference_high: 5.1,
  standing: "needs_attention",
  direction: "above",
  message: "Please call the clinic today.",
  shared_at: "2026-10-10T09:00:00",
  viewed_at: null,
  ...over,
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <PortalLabsPage />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

const items = () => within(screen.getByRole("list")).getAllByRole("listitem");

describe("PortalLabsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("cac_lang");
  });

  it("shows each communicated result with its value, range, explanation and the clinician's message", async () => {
    vi.spyOn(api, "portalLabs").mockResolvedValue({ patient_id: "p", labs: [lab()] });
    renderPage();

    const [card] = await waitForItems();
    expect(within(card).getByText("Potassium")).toBeInTheDocument();
    expect(within(card).getByText("6.4 mmol/L")).toBeInTheDocument();
    expect(within(card).getByText(/Usual range/)).toBeInTheDocument();
    expect(within(card).getByText("3.5–5.1 mmol/L")).toBeInTheDocument();
    expect(within(card).getByText(/Your Potassium needs attention soon/)).toBeInTheDocument();
    expect(within(card).getByText("Please call the clinic today.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open this result" })).toHaveAttribute("href", "/portal/results/s-1");
  });

  it("marks a result nobody has opened as new, and only that one", async () => {
    vi.spyOn(api, "portalLabs").mockResolvedValue({
      patient_id: "p",
      labs: [lab(), lab({ share_id: "s-2", test_name: "sodium", viewed_at: "2026-10-11T08:00:00" })],
    });
    renderPage();

    const [fresh, read] = await waitForItems(2);
    expect(within(fresh).getByText("New")).toBeInTheDocument();
    expect(within(read).queryByText("New")).not.toBeInTheDocument();
  });

  it("says plainly when nothing has been shared yet", async () => {
    vi.spyOn(api, "portalLabs").mockResolvedValue({ patient_id: "p", labs: [] });
    renderPage();

    expect(await screen.findByText("Your care team has not shared any lab results with you yet.")).toBeInTheDocument();
    expect(screen.queryByText(/Only your care team can tell you/)).not.toBeInTheDocument();
  });

  it("shows a loading state, then an error it can announce", async () => {
    vi.spyOn(api, "portalLabs").mockRejectedValue(new Error("500"));
    renderPage();

    expect(screen.getByText("Loading your labs…")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("We could not load your labs");
  });

  it("never shows anything about the review behind a result", async () => {
    vi.spyOn(api, "portalLabs").mockResolvedValue({ patient_id: "p", labs: [lab()] });
    renderPage();
    await waitForItems();

    expect(document.body.textContent).not.toMatch(/disposition|classification|needs_patient_contact|severity/i);
  });

  it("speaks Spanish, with the explanation and the notice", async () => {
    localStorage.setItem("cac_lang", "es");
    vi.spyOn(api, "portalLabs").mockResolvedValue({ patient_id: "p", labs: [lab({ standing: "inside", direction: null })] });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Mis laboratorios" })).toBeInTheDocument();
    expect(await screen.findByText("Tu Potasio está dentro del rango habitual.")).toBeInTheDocument();
    expect(screen.getByText(/Solo tu equipo de salud puede decirte/)).toBeInTheDocument();
    expect(screen.getByText("Nuevo")).toBeInTheDocument();
  });
});

async function waitForItems(count = 1) {
  await screen.findByText("Potassium");
  const found = items();
  expect(found).toHaveLength(count);
  return found;
}
