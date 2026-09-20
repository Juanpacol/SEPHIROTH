import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { clearAuth, storeAuth, type AuthUser } from "@/lib/auth";

const USER: AuthUser = {
  id: "u1",
  email: "doc@example.org",
  name: "Dr. Test",
  role: "clinician",
  patient_id: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api fetch helpers (via api.*)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the Authorization header from localStorage on a GET", async () => {
    storeAuth("tok-xyz", USER);
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse([]));

    await api.patients();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.headers).toEqual({ Authorization: "Bearer tok-xyz" });
  });

  it("sends no Authorization header when logged out", async () => {
    clearAuth();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse([]));

    await api.patients();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.headers).toEqual({});
  });

  it("POSTs JSON with Content-Type and the auth header together", async () => {
    storeAuth("tok-abc", USER);
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse({ access_token: "t", token_type: "bearer", user: USER }, 201)
    );

    await api.register({ email: "a@b.com", name: "A", password: "password123" });

    const [path, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(path).toBe("/api/auth/register");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json", Authorization: "Bearer tok-abc" });
    expect(JSON.parse(init.body)).toEqual({ email: "a@b.com", name: "A", password: "password123" });
  });

  it("throws ApiError with the status code on a non-2xx, non-401/403 response", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("Patient not found", { status: 404 })
    );

    await expect(api.patient("does-not-exist")).rejects.toMatchObject({
      status: 404,
    });
  });

  it("throws a 403 ApiError with a friendly message, without redirecting", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("", { status: 403 }));

    let caught: unknown;
    try {
      await api.patients();
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(403);
  });

  it("redirects to /login and throws a 401 ApiError on an expired/invalid token", async () => {
    const original = window.location;
    // jsdom's window.location isn't directly assignable; delete+redefine.
    // @ts-expect-error -- intentional override for this test only
    delete window.location;
    // @ts-expect-error -- window.location's setter type is oddly `string & Location`
    window.location = { ...original, href: "", pathname: "/dashboard" };

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("", { status: 401 }));

    await expect(api.patients()).rejects.toMatchObject({ status: 401 });
    expect(window.location.href).toBe("/login");

    // @ts-expect-error -- restoring the original, same setter-type quirk as above
    window.location = original;
  });

  it("changePassword on a 500 rejects with ApiError whose message is the raw body, no status prefix", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("bad request body", { status: 500 }));

    let caught: unknown;
    try {
      await api.changePassword({ current_password: "a", new_password: "b" });
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(500);
    expect((caught as ApiError).message).toBe("bad request body");
  });

  it("changePassword on a 401 rejects with ApiError 401 and does not navigate", async () => {
    const original = window.location;
    // @ts-expect-error -- intentional override for this test only
    delete window.location;
    // @ts-expect-error -- window.location's setter type is oddly `string & Location`
    window.location = { ...original, href: "", pathname: "/profile" };

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("", { status: 401 }));

    await expect(api.changePassword({ current_password: "a", new_password: "b" })).rejects.toMatchObject({
      status: 401,
    });
    expect(window.location.href).toBe("");

    // @ts-expect-error -- restoring the original, same setter-type quirk as above
    window.location = original;
  });

  it("markNotificationRead on a 401 rejects with ApiError 401 and does redirect (default redirect-on-401)", async () => {
    const original = window.location;
    // @ts-expect-error -- intentional override for this test only
    delete window.location;
    // @ts-expect-error -- window.location's setter type is oddly `string & Location`
    window.location = { ...original, href: "", pathname: "/dashboard" };

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("", { status: 401 }));

    await expect(api.markNotificationRead("n1")).rejects.toMatchObject({ status: 401 });
    expect(window.location.href).toBe("/login");

    // @ts-expect-error -- restoring the original, same setter-type quirk as above
    window.location = original;
  });

  it("exportConsultation on a 404 rejects with ApiError 404", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("not found", { status: 404 }));

    await expect(api.exportConsultation("c1")).rejects.toMatchObject({ status: 404 });
  });

  it("exportConsultation on a 401 rejects with ApiError 401 and redirects", async () => {
    const original = window.location;
    // @ts-expect-error -- intentional override for this test only
    delete window.location;
    // @ts-expect-error -- window.location's setter type is oddly `string & Location`
    window.location = { ...original, href: "", pathname: "/dashboard" };

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(new Response("", { status: 401 }));

    await expect(api.exportConsultation("c1")).rejects.toMatchObject({ status: 401 });
    expect(window.location.href).toBe("/login");

    // @ts-expect-error -- restoring the original, same setter-type quirk as above
    window.location = original;
  });
});
