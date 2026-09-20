import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";
import { api } from "@/lib/api";
import en from "@/lib/i18n/dictionaries.en";
import { LanguageProvider } from "@/lib/language";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    login: vi.fn(),
    register: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

function renderPage() {
  return render(
    <LanguageProvider>
      <LoginPage />
    </LanguageProvider>
  );
}

function submitButton(): HTMLElement {
  return screen.getAllByRole("button").find((b) => b.getAttribute("type") === "submit")!;
}

async function submitLogin(email = "doc@example.org", password = "password123") {
  fireEvent.change(screen.getByPlaceholderText("you@hospital.org"), { target: { value: email } });
  fireEvent.change(screen.getByPlaceholderText(en["login.passwordPlaceholder"]), {
    target: { value: password },
  });
  fireEvent.click(submitButton());
}

describe("LoginPage error classification", () => {
  beforeEach(() => {
    push.mockClear();
    vi.mocked(api.login).mockReset();
    vi.mocked(api.register).mockReset();
  });

  afterEach(() => vi.clearAllMocks());

  it("renders invalidCredentials on a 401", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.login).mockRejectedValueOnce(new ApiError(401, "Not authenticated"));

    renderPage();
    await submitLogin();

    await waitFor(() =>
      expect(screen.getByText(en["login.error.invalidCredentials"])).toBeInTheDocument()
    );
  });

  it("renders emailTaken on a 409 during registration", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.register).mockRejectedValueOnce(
      new ApiError(409, '{"detail":"Email already registered"}')
    );

    renderPage();
    fireEvent.click(screen.getByText(en["login.registerAsClinician"]));
    fireEvent.change(screen.getByPlaceholderText(en["login.fullNamePlaceholder"]), {
      target: { value: "Dr. Test" },
    });
    await submitLogin();

    await waitFor(() => expect(screen.getByText(en["login.error.emailTaken"])).toBeInTheDocument());
  });

  it("renders validation on a 422", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.login).mockRejectedValueOnce(new ApiError(422, '{"detail":[]}'));

    renderPage();
    await submitLogin();

    await waitFor(() => expect(screen.getByText(en["login.error.validation"])).toBeInTheDocument());
  });

  it("renders serverUnreachable on a network failure", async () => {
    vi.mocked(api.login).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    renderPage();
    await submitLogin();

    await waitFor(() =>
      expect(screen.getByText(en["login.error.serverUnreachable"])).toBeInTheDocument()
    );
  });

  it("renders tooManyAttempts on a 429", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.login).mockRejectedValueOnce(new ApiError(429, "rate limited"));

    renderPage();
    await submitLogin();

    await waitFor(() =>
      expect(screen.getByText(en["login.error.tooManyAttempts"])).toBeInTheDocument()
    );
  });

  it("renders accountLocked on a 403 in login mode", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.login).mockRejectedValueOnce(
      new ApiError(403, "This isn't available for your account.")
    );

    renderPage();
    await submitLogin();

    await waitFor(() => expect(screen.getByText(en["login.error.accountLocked"])).toBeInTheDocument());
  });

  it("renders registrationRestricted on a 403 in register mode", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.register).mockRejectedValueOnce(
      new ApiError(403, "This isn't available for your account.")
    );

    renderPage();
    fireEvent.click(screen.getByText(en["login.registerAsClinician"]));
    fireEvent.change(screen.getByPlaceholderText(en["login.fullNamePlaceholder"]), {
      target: { value: "Dr. Test" },
    });
    await submitLogin();

    await waitFor(() =>
      expect(screen.getByText(en["login.error.registrationRestricted"])).toBeInTheDocument()
    );
  });
});
