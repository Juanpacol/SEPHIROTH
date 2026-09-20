import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProfilePage from "@/app/profile/page";
import { api } from "@/lib/api";
import { storeAuth, type AuthUser } from "@/lib/auth";
import en from "@/lib/i18n/dictionaries.en";
import { LanguageProvider } from "@/lib/language";

vi.mock("@/lib/api", () => ({
  api: {
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
    me: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

const USER: AuthUser = {
  id: "u1",
  email: "doc@example.org",
  name: "Dr. Test",
  role: "clinician",
  patient_id: null,
};

function renderPage() {
  return render(
    <LanguageProvider>
      <ProfilePage />
    </LanguageProvider>
  );
}

function saveProfileButton(): HTMLElement {
  return screen.getByRole("button", { name: en["profile.saveChanges"] });
}

function changePasswordButton(): HTMLElement {
  return screen.getByRole("button", { name: en["profile.changePassword"] });
}

function fillPasswordForm(current: string, next: string, confirm: string) {
  const inputs = document.querySelectorAll<HTMLInputElement>('input[type="password"]');
  fireEvent.change(inputs[0], { target: { value: current } });
  fireEvent.change(inputs[1], { target: { value: next } });
  fireEvent.change(inputs[2], { target: { value: confirm } });
}

describe("ProfilePage error classification", () => {
  beforeEach(() => {
    storeAuth("tok-1", USER);
    vi.mocked(api.updateProfile).mockReset();
    vi.mocked(api.changePassword).mockReset();
    vi.mocked(api.me).mockReset();
    // ThemeToggle (rendered on this page) reads window.matchMedia; jsdom has no implementation.
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }))
    );
  });

  afterEach(() => vi.clearAllMocks());

  it("renders emailTaken on a 409 from updateProfile", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.updateProfile).mockRejectedValueOnce(
      new ApiError(409, '{"detail":"Email already registered"}')
    );

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fireEvent.click(saveProfileButton());

    await waitFor(() => expect(screen.getByText(en["profile.error.emailTaken"])).toBeInTheDocument());
  });

  it("renders saveFailed on a 500 from updateProfile", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.updateProfile).mockRejectedValueOnce(new ApiError(500, "boom"));

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fireEvent.click(saveProfileButton());

    await waitFor(() => expect(screen.getByText(en["profile.error.saveFailed"])).toBeInTheDocument());
  });

  it("renders currentPasswordIncorrect when changePassword 401s and the session probe succeeds", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.changePassword).mockRejectedValueOnce(new ApiError(401, "Not authenticated"));
    vi.mocked(api.me).mockResolvedValueOnce(USER as never);

    const original = window.location;
    // @ts-expect-error -- intentional override for this test only
    delete window.location;
    // @ts-expect-error -- window.location's setter type is oddly `string & Location`
    window.location = { ...original, href: "", pathname: "/profile" };

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fillPasswordForm("wrongpass", "newpassword123", "newpassword123");
    fireEvent.click(changePasswordButton());

    await waitFor(() =>
      expect(screen.getByText(en["profile.error.currentPasswordIncorrect"])).toBeInTheDocument()
    );
    expect(api.me).toHaveBeenCalledTimes(1);
    expect(window.location.href).toBe("");

    // @ts-expect-error -- restoring the original, same setter-type quirk as above
    window.location = original;
  });

  it("renders no inline error when changePassword 401s and the session probe also 401s (session dead)", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.changePassword).mockRejectedValueOnce(new ApiError(401, "Not authenticated"));
    vi.mocked(api.me).mockRejectedValueOnce(new ApiError(401, "Not authenticated"));

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fillPasswordForm("wrongpass", "newpassword123", "newpassword123");
    fireEvent.click(changePasswordButton());

    await waitFor(() => expect(changePasswordButton()).not.toBeDisabled());
    expect(
      screen.queryByText(en["profile.error.currentPasswordIncorrect"])
    ).not.toBeInTheDocument();
    expect(screen.queryByText(en["profile.error.passwordChangeFailed"])).not.toBeInTheDocument();
  });

  it("renders passwordChangeFailed when changePassword 401s and the probe fails with a network error", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.changePassword).mockRejectedValueOnce(new ApiError(401, "Not authenticated"));
    vi.mocked(api.me).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fillPasswordForm("wrongpass", "newpassword123", "newpassword123");
    fireEvent.click(changePasswordButton());

    await waitFor(() =>
      expect(screen.getByText(en["profile.error.passwordChangeFailed"])).toBeInTheDocument()
    );
  });

  it("renders passwordChangeFailed on a 500 without probing the session", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.changePassword).mockRejectedValueOnce(new ApiError(500, "boom"));

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fillPasswordForm("current", "newpassword123", "newpassword123");
    fireEvent.click(changePasswordButton());

    await waitFor(() =>
      expect(screen.getByText(en["profile.error.passwordChangeFailed"])).toBeInTheDocument()
    );
    expect(api.me).not.toHaveBeenCalled();
  });

  it("renders passwordMismatch and does not call the API when new/confirm differ", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fillPasswordForm("current", "newpassword123", "somethingelse");
    fireEvent.click(changePasswordButton());

    await waitFor(() =>
      expect(screen.getByText(en["profile.error.passwordMismatch"])).toBeInTheDocument()
    );
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it("re-enables the submit button after a failed attempt that goes through the probe", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.changePassword).mockRejectedValueOnce(new ApiError(401, "Not authenticated"));
    vi.mocked(api.me).mockResolvedValueOnce(USER as never);

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue(USER.email)).toBeInTheDocument());
    fillPasswordForm("wrongpass", "newpassword123", "newpassword123");
    fireEvent.click(changePasswordButton());

    await waitFor(() => expect(changePasswordButton()).not.toBeDisabled());
  });
});
