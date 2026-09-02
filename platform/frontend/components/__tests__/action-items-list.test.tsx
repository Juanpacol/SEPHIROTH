import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ActionItemsList, { itemText } from "@/components/action-items-list";
import { api } from "@/lib/api";
import type { DashboardActionItem } from "@/lib/api";
import { LanguageProvider, useLanguage } from "@/lib/language";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { ...actual.api, markActedOn: vi.fn() } };
});

const showToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({ useToast: () => showToast }));

function baseItem(overrides: Partial<DashboardActionItem>): DashboardActionItem {
  return {
    category: "alert",
    severity: "high",
    patient_id: "P1",
    patient_name: "Juan Pérez",
    ...overrides,
  };
}

function renderList(items: DashboardActionItem[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ActionItemsList items={items} />
      </LanguageProvider>
    </QueryClientProvider>
  );
}

describe("itemText — alert category", () => {
  // Renders `t` from within a LanguageProvider so the plain-language
  // template actually resolves instead of returning a raw i18n key.
  function withEnglish(item: DashboardActionItem): string {
    let result = "";
    function Probe() {
      const { t } = useLanguage();
      result = itemText(item, t);
      return null;
    }
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>
    );
    return result;
  }

  it("rewrites a drug-interaction alert into plain language, dropping the DDInter jargon", () => {
    const item = baseItem({
      title: "Interaction: clopidogrel + warfarin",
      detail:
        "Potentially serious interaction — increased risk of significant adverse effects (per DDInter 2.0 severity classification).",
    });
    const text = withEnglish(item);
    expect(text).toContain("clopidogrel");
    expect(text).toContain("warfarin");
    expect(text).not.toContain("DDInter");
    expect(text).not.toContain("classification");
  });

  it("leaves a non-interaction alert's title/detail as authored", () => {
    const item = baseItem({ title: "Severe obesity", detail: "BMI 46.6 (≥ 40)" });
    const text = withEnglish(item);
    expect(text).toBe("Severe obesity — BMI 46.6 (≥ 40)");
  });
});

describe("ActionItemsList", () => {
  it("renders the patient-facing simplified interaction line, not the raw alert text", () => {
    renderList([
      baseItem({
        title: "Interaction: clopidogrel + warfarin",
        detail: "Potentially serious interaction (per DDInter 2.0 severity classification).",
      }),
    ]);
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
    expect(screen.queryByText(/DDInter/)).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no items", () => {
    renderList([]);
    expect(screen.getByText(/caught up|todo al día/i)).toBeInTheDocument();
  });

  it("resolves a decision item without navigating to the patient page", async () => {
    vi.mocked(api.markActedOn).mockResolvedValue({} as never);
    renderList([
      baseItem({
        category: "decision",
        consultation_id: "C1",
        query_preview: "Should we escalate this patient's care?",
      }),
    ]);

    fireEvent.click(screen.getByText("I acted on this"));

    await waitFor(() => expect(api.markActedOn).toHaveBeenCalledWith("C1", true));
    expect(showToast).toHaveBeenCalled();
  });
});
