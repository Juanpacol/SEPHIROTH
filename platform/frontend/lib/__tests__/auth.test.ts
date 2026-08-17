import { beforeEach, describe, expect, it } from "vitest";
import { authHeaders, clearAuth, getStoredUser, getToken, homeFor, storeAuth, type AuthUser } from "@/lib/auth";

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

describe("homeFor", () => {
  it("sends a patient to /portal", () => {
    expect(homeFor("patient")).toBe("/portal");
  });

  it("sends a clinician to /dashboard", () => {
    expect(homeFor("clinician")).toBe("/dashboard");
  });
});

describe("storeAuth / getStoredUser / getToken / clearAuth", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips a token and user through localStorage", () => {
    storeAuth("tok-123", CLINICIAN);
    expect(getToken()).toBe("tok-123");
    expect(getStoredUser()).toEqual(CLINICIAN);
  });

  it("returns null for both when nothing is stored", () => {
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it("clears both token and user", () => {
    storeAuth("tok-123", PATIENT);
    clearAuth();
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });
});

describe("authHeaders", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns an empty object when no token is stored", () => {
    expect(authHeaders()).toEqual({});
  });

  it("returns a Bearer header when a token is stored", () => {
    storeAuth("tok-abc", CLINICIAN);
    expect(authHeaders()).toEqual({ Authorization: "Bearer tok-abc" });
  });
});
