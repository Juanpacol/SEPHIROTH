import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NotificationBell from "@/components/notification-bell";
import { api } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function renderBell() {
  return render(
    <LanguageProvider>
      <NotificationBell />
    </LanguageProvider>
  );
}

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    unreadNotificationCount: vi.fn(),
    listNotifications: vi.fn(),
    markNotificationRead: vi.fn(),
  },
}));

describe("NotificationBell", () => {
  beforeEach(() => {
    vi.mocked(api.unreadNotificationCount).mockResolvedValue({ count: 2 });
    vi.mocked(api.listNotifications).mockResolvedValue([
      {
        id: "n1",
        type: "appointment_booked",
        message: "Your appointment is confirmed.",
        related_appointment_id: "a1",
        read_at: null,
        created_at: "2026-01-01T00:00:00",
      },
    ]);
    vi.mocked(api.markNotificationRead).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the unread count badge after polling", async () => {
    renderBell();
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
  });

  it("opens the dropdown and lists notifications on click", async () => {
    renderBell();
    await waitFor(() => expect(api.unreadNotificationCount).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("Notifications"));

    await waitFor(() => expect(screen.getByText("Your appointment is confirmed.")).toBeInTheDocument());
  });

  it("marks a notification read on click and decrements the badge", async () => {
    renderBell();
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Notifications"));
    await waitFor(() => expect(screen.getByText("Your appointment is confirmed.")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Your appointment is confirmed."));

    await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledWith("n1"));
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });
});
