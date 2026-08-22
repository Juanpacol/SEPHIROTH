import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FollowupCard from "@/components/patients/followup-card";
import { api } from "@/lib/api";

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FollowupCard patientId="P001" />
    </QueryClientProvider>
  );
}

vi.mock("@/lib/api", () => ({
  api: {
    listFollowupPlans: vi.fn(),
    createFollowupPlan: vi.fn(),
    cancelFollowupPlan: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

const showToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => showToast,
}));

describe("FollowupCard", () => {
  beforeEach(() => {
    showToast.mockClear();
    vi.mocked(api.listFollowupPlans).mockReset();
    vi.mocked(api.createFollowupPlan).mockReset();
  });

  afterEach(() => vi.clearAllMocks());

  it("shows the create form when there is no active plan", async () => {
    vi.mocked(api.listFollowupPlans).mockResolvedValue([]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Start follow-up plan")).toBeInTheDocument());
  });

  it("creates a follow-up plan with the given instructions", async () => {
    vi.mocked(api.listFollowupPlans).mockResolvedValue([]);
    vi.mocked(api.createFollowupPlan).mockResolvedValue({
      id: "FP1",
      patient_id: "P001",
      consultation_id: null,
      created_by_user_id: "U1",
      status: "active",
      instructions: "Check in on new prescription",
      created_at: "2026-08-01T00:00:00",
      completed_at: null,
    });
    renderCard();

    await waitFor(() => expect(screen.getByText("Start follow-up plan")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/day 3\/7\/30/i), {
      target: { value: "Check in on new prescription" },
    });
    fireEvent.click(screen.getByText("Start follow-up plan"));

    await waitFor(() =>
      expect(api.createFollowupPlan).toHaveBeenCalledWith({
        patient_id: "P001",
        instructions: "Check in on new prescription",
      })
    );
  });

  it("shows the active plan instead of the create form", async () => {
    vi.mocked(api.listFollowupPlans).mockResolvedValue([
      {
        id: "FP1",
        patient_id: "P001",
        consultation_id: null,
        created_by_user_id: "U1",
        status: "active",
        instructions: "Watch for dizziness",
        created_at: "2026-08-01T00:00:00",
        completed_at: null,
      },
    ]);
    renderCard();

    await waitFor(() => expect(screen.getByText("Watch for dizziness")).toBeInTheDocument());
    expect(screen.queryByText("Start follow-up plan")).not.toBeInTheDocument();
  });
});
