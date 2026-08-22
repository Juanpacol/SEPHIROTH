import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AlertsPage from "@/app/alerts/page";
import { api } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <AlertsPage />
      </LanguageProvider>
    </QueryClientProvider>
  );
}

vi.mock("@/lib/api", () => ({
  api: {
    listAlerts: vi.fn(),
    reviewAlert: vi.fn(),
    resolveAlert: vi.fn(),
  },
}));

const showToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => showToast,
}));

const activeAlert = {
  id: "AL1",
  patient_id: "P001",
  category: "lab",
  severity: "critical" as const,
  status: "active" as const,
  title: "Critical potassium",
  detail: "Potassium 6.2 mmol/L",
  source: "risk_engine",
  assigned_to_user_id: null,
  due_at: null,
  reviewed_at: null,
  reviewed_by: null,
  resolved_at: null,
  escalated_at: null,
  created_at: "2026-08-01T00:00:00",
};

describe("AlertsPage", () => {
  beforeEach(() => {
    showToast.mockClear();
    vi.mocked(api.listAlerts).mockReset();
    vi.mocked(api.reviewAlert).mockReset();
    vi.mocked(api.resolveAlert).mockReset();
  });

  afterEach(() => vi.clearAllMocks());

  it("shows the empty state", async () => {
    vi.mocked(api.listAlerts).mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByText("Nothing here.")).toBeInTheDocument());
  });

  it("reviews an active alert", async () => {
    vi.mocked(api.listAlerts).mockResolvedValue([activeAlert]);
    vi.mocked(api.reviewAlert).mockResolvedValue({ ...activeAlert, status: "reviewed" });
    renderPage();

    await waitFor(() => expect(screen.getByText("Critical potassium")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Mark reviewed"));

    await waitFor(() => expect(api.reviewAlert).toHaveBeenCalledWith("AL1"));
    expect(showToast).toHaveBeenCalledWith("Marked reviewed.");
  });

  it("does not offer resolve on an active (not-yet-reviewed) alert", async () => {
    vi.mocked(api.listAlerts).mockResolvedValue([activeAlert]);
    renderPage();

    await waitFor(() => expect(screen.getByText("Critical potassium")).toBeInTheDocument());
    expect(screen.queryByText("Resolve")).not.toBeInTheDocument();
  });
});
