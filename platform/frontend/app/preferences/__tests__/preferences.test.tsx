import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PreferencesPage from "@/app/preferences/page";
import { api } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

vi.mock("@/lib/api", () => ({
  api: {
    readAutomationMemory: vi.fn(),
    writeAutomationMemory: vi.fn(),
  },
}));

function renderPage() {
  return render(
    <LanguageProvider>
      <PreferencesPage />
    </LanguageProvider>
  );
}

describe("PreferencesPage", () => {
  beforeEach(() => {
    vi.mocked(api.readAutomationMemory).mockReset();
    vi.mocked(api.writeAutomationMemory).mockReset();
    vi.mocked(api.readAutomationMemory).mockResolvedValue({
      scope: "clinic",
      scope_id: "default",
      key: "reminder_lead_hours",
      value: null,
    });
  });

  afterEach(() => vi.clearAllMocks());

  it("renders both preference forms with their defaults", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Reminder lead time")).toBeInTheDocument());
    expect(screen.getByText("Quiet hours")).toBeInTheDocument();
    expect(screen.getByDisplayValue("24")).toBeInTheDocument();
  });

  it("saves the reminder lead time", async () => {
    vi.mocked(api.writeAutomationMemory).mockResolvedValue({
      scope: "clinic",
      scope_id: "default",
      key: "reminder_lead_hours",
      value: 48,
    });
    renderPage();

    await waitFor(() => expect(screen.getByDisplayValue("24")).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue("24"), { target: { value: "48" } });
    fireEvent.click(screen.getAllByText("Save")[0]);

    await waitFor(() =>
      expect(api.writeAutomationMemory).toHaveBeenCalledWith("clinic", "default", "reminder_lead_hours", 48)
    );
  });
});
