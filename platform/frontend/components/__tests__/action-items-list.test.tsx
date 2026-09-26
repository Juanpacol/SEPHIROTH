import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ActionItemsList, { itemText } from "@/components/action-items-list";
import { api } from "@/lib/api";
import type { DashboardActionGroup, DashboardActionItem } from "@/lib/api";
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

function group(items: DashboardActionItem[]): DashboardActionGroup {
  return {
    patient_id: items[0].patient_id,
    patient_name: items[0].patient_name,
    severity: items[0].severity,
    items,
  };
}

function renderList(groups: DashboardActionGroup[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ActionItemsList groups={groups} />
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
      group([
        baseItem({
          title: "Interaction: clopidogrel + warfarin",
          detail: "Potentially serious interaction (per DDInter 2.0 severity classification).",
        }),
      ]),
    ]);
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
    expect(screen.queryByText(/DDInter/)).not.toBeInTheDocument();
  });

  it("renders one card per patient with every signal inside it", () => {
    renderList([
      group([
        baseItem({ severity: "critical", title: "Hypertensive range", detail: "BP 185/112" }),
        baseItem({ category: "lab", severity: "high", test_name: "potassium", value: 6.8, unit: "mmol/L" }),
      ]),
      group([baseItem({ patient_id: "P2", patient_name: "María López", category: "followup", severity: "medium" })]),
    ]);

    expect(screen.getAllByText("Juan Pérez")).toHaveLength(1);
    expect(screen.getByText(/Hypertensive range/)).toBeInTheDocument();
    expect(screen.getByText(/6\.8/)).toBeInTheDocument();
    expect(screen.getByText("María López")).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("shows the empty state when there are no items", () => {
    renderList([]);
    expect(screen.getByText(/caught up|todo al día/i)).toBeInTheDocument();
  });

  it("resolves a decision item without navigating to the patient page", async () => {
    vi.mocked(api.markActedOn).mockResolvedValue({} as never);
    renderList([
      group([
        baseItem({
          category: "decision",
          consultation_id: "C1",
          query_preview: "Should we escalate this patient's care?",
        }),
      ]),
    ]);

    fireEvent.click(screen.getByText("I acted on this"));

    await waitFor(() => expect(api.markActedOn).toHaveBeenCalledWith("C1", true));
    expect(showToast).toHaveBeenCalled();
  });
});
