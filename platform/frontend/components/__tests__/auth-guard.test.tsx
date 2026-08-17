import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AuthGuard from "@/components/auth-guard";
import { clearAuth, storeAuth, type AuthUser } from "@/lib/auth";

const replace = vi.fn();
let mockPathname = "/dashboard";

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace }),
}));

const CLINICIAN: AuthUser = {
  id: "u1",
  email: "doc@example.org",
  name: "Dr. Test",
  role: "clinician",
  patient_id: null,
};

const PATIENT: AuthUser = {
  id: "u2",
  email: "patient@example.org",
  name: "Patient Test",
  role: "patient",
  patient_id: "P1",
};

describe("AuthGuard", () => {
  beforeEach(() => {
    localStorage.clear();
    replace.mockClear();
    mockPathname = "/dashboard";
  });

  afterEach(() => {
    window.location.href = "about:blank";
  });

  it("renders children once a correctly-roled user is found", async () => {
    storeAuth("tok", CLINICIAN);
    mockPathname = "/dashboard";

    render(
      <AuthGuard>
        <div>protected content</div>
      </AuthGuard>
    );

    await waitFor(() => expect(screen.getByText("protected content")).toBeInTheDocument());
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects a patient away from a clinician route", async () => {
    storeAuth("tok", PATIENT);
    mockPathname = "/dashboard";

    render(
      <AuthGuard>
        <div>clinician-only content</div>
      </AuthGuard>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal"));
    expect(screen.queryByText("clinician-only content")).not.toBeInTheDocument();
  });

  it("redirects a clinician away from a patient route", async () => {
    storeAuth("tok", CLINICIAN);
    mockPathname = "/portal";

    render(
      <AuthGuard>
        <div>patient-only content</div>
      </AuthGuard>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("patient-only content")).not.toBeInTheDocument();
  });

  it("renders nothing and does not redirect via router when logged out", async () => {
    clearAuth();
    mockPathname = "/dashboard";

    const { container } = render(
      <AuthGuard>
        <div>should not appear</div>
      </AuthGuard>
    );

    await waitFor(() => expect(screen.queryByText("should not appear")).not.toBeInTheDocument());
    expect(container).toBeEmptyDOMElement();
    expect(replace).not.toHaveBeenCalled();
  });
});
