import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ApprovalsPage from "@/app/approvals/page";
import { api } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ApprovalsPage />
      </LanguageProvider>
    </QueryClientProvider>
  );
}

vi.mock("@/lib/api", () => ({
  api: {
    listPendingActions: vi.fn(),
    draftPendingAction: vi.fn(),
    approvePendingAction: vi.fn(),
    rejectPendingAction: vi.fn(),
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

const pendingAction = {
  id: "PA1",
  workflow_step_id: null,
  patient_id: "P001",
  patient_name: "Jane Doe",
  action_type: "followup_day3",
  instructions: null,
  status: "pending" as const,
  draft_text: "Hi, checking in on you.",
  draft_source: "llm" as const,
  draft_model: "gemini-flash-latest",
  final_text: "",
  edited: false,
  assigned_to_user_id: null,
  expires_at: null,
  reviewed_by: null,
  reviewed_at: null,
  reject_reason: "",
  created_at: "2026-08-01T00:00:00",
};

describe("ApprovalsPage", () => {
  beforeEach(() => {
    showToast.mockClear();
    vi.mocked(api.listPendingActions).mockReset();
    vi.mocked(api.approvePendingAction).mockReset();
    vi.mocked(api.rejectPendingAction).mockReset();
  });

  afterEach(() => vi.clearAllMocks());

  it("shows the empty state when there is nothing pending", async () => {
    vi.mocked(api.listPendingActions).mockResolvedValue([]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Nothing is waiting for your approval right now.")).toBeInTheDocument()
    );
  });

  it("lists a pending action (by patient name) and approves it", async () => {
    vi.mocked(api.listPendingActions).mockResolvedValue([pendingAction]);
    vi.mocked(api.approvePendingAction).mockResolvedValue({ ...pendingAction, status: "approved" });
    renderPage();

    await waitFor(() => expect(screen.getAllByText("Jane Doe").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/day 3 follow-up/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("Approve"));

    await waitFor(() =>
      expect(api.approvePendingAction).toHaveBeenCalledWith("PA1", "Hi, checking in on you.")
    );
    expect(showToast).toHaveBeenCalledWith("Approved and sent to the patient.");
  });

  it("requires a reason before confirming a reject", async () => {
    vi.mocked(api.listPendingActions).mockResolvedValue([pendingAction]);
    renderPage();

    await waitFor(() => expect(screen.getByText("Reject")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Reject"));

    const confirmButton = screen.getByText("Confirm reject") as HTMLButtonElement;
    expect(confirmButton.disabled).toBe(true);
  });
});
