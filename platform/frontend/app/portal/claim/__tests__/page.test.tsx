import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ClaimInvitePage from "@/app/portal/claim/page";
import { clearAuth, storeAuth, type AuthUser } from "@/lib/auth";
import { LanguageProvider } from "@/lib/language";

const replace = vi.fn();
const push = vi.fn();
let mockSearch = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push }),
  useSearchParams: () => mockSearch,
}));

function renderPage() {
  return render(
    <LanguageProvider>
      <ClaimInvitePage />
    </LanguageProvider>
  );
}

const PATIENT: AuthUser = {
  id: "u1",
  email: "patient@example.org",
  name: "Patient Test",
  role: "patient",
  patient_id: "P1",
};

describe("ClaimInvitePage", () => {
  beforeEach(() => {
    localStorage.clear();
    replace.mockClear();
    push.mockClear();
    mockSearch = new URLSearchParams();
  });

  afterEach(() => {
    window.location.href = "about:blank";
  });

  it("redirects an already-logged-in user back to their portal instead of showing the form again", async () => {
    storeAuth("tok", PATIENT);
    mockSearch = new URLSearchParams({ code: "3.some-secret" });

    renderPage();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal"));
    expect(screen.queryByText("Set up your portal account")).not.toBeInTheDocument();
  });

  it("shows an incomplete-link message, not a code field, when the link has no code", async () => {
    clearAuth();
    mockSearch = new URLSearchParams();

    renderPage();

    await waitFor(() => expect(screen.getByText("This invite link is incomplete")).toBeInTheDocument());
    expect(screen.queryByLabelText(/claim code/i)).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows the setup form with no visible code field when a valid link code is present", async () => {
    clearAuth();
    mockSearch = new URLSearchParams({ code: "3.some-secret" });

    renderPage();

    await waitFor(() => expect(screen.getByText("Set up your portal account")).toBeInTheDocument());
    expect(screen.queryByText(/claim code/i)).not.toBeInTheDocument();
    expect(screen.getByText("Full name")).toBeInTheDocument();
  });
});
