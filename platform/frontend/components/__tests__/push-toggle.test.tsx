/** The notification toggle's four states.
 *
 * The important one is that the permission prompt fires from a click and from
 * nowhere else. An unsolicited prompt is answered "block", and a blocked
 * permission cannot be asked for again by the page — so getting this wrong
 * costs the user the feature permanently, not just this once.
 *
 * "Not supported" and "not configured" are kept apart deliberately: the first
 * is the user's browser and the second is an operator's `.env`, and collapsing
 * them means nobody can tell which one to fix.
 *
 * Verifies AC-025-11 (docs/specs/SPEC-025-pwa-push.md).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PushToggle from "@/components/settings/push-toggle";
import { LanguageProvider } from "@/lib/language";

const pushKey = vi.fn();
const pushDevices = vi.fn();
const enablePush = vi.fn();
const disablePush = vi.fn();
const pushSupport = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, pushKey: () => pushKey(), pushDevices: () => pushDevices() },
  };
});

vi.mock("@/lib/push", () => ({
  enablePush: () => enablePush(),
  disablePush: () => disablePush(),
  pushSupport: () => pushSupport(),
}));

function renderToggle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <PushToggle />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

const enableButton = () => screen.getByRole("button", { name: /activar|turn on/i });

describe("PushToggle", () => {
  beforeEach(() => {
    pushKey.mockReset().mockResolvedValue({ enabled: true, public_key: "pub" });
    pushDevices.mockReset().mockResolvedValue({ items: [] });
    enablePush.mockReset();
    disablePush.mockReset();
    pushSupport.mockReset().mockReturnValue("default");
  });

  afterEach(() => vi.clearAllMocks());

  it("does not ask for permission on mount", async () => {
    renderToggle();

    await waitFor(() => expect(enableButton()).toBeInTheDocument());
    expect(enablePush).not.toHaveBeenCalled();
  });

  it("asks only when the button is pressed", async () => {
    enablePush.mockResolvedValue({ ok: true, permission: "granted" });
    renderToggle();
    await waitFor(() => enableButton());

    fireEvent.click(enableButton());

    await waitFor(() => expect(enablePush).toHaveBeenCalledTimes(1));
  });

  it("offers to turn it off once it is on", async () => {
    pushSupport.mockReturnValue("granted");
    renderToggle();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /desactivar|turn off/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /activar|turn on/i })).not.toBeInTheDocument();
  });

  it("unsubscribes when turned off", async () => {
    pushSupport.mockReturnValue("granted");
    disablePush.mockResolvedValue(undefined);
    renderToggle();
    await waitFor(() => screen.getByRole("button", { name: /desactivar|turn off/i }));

    fireEvent.click(screen.getByRole("button", { name: /desactivar|turn off/i }));

    await waitFor(() => expect(disablePush).toHaveBeenCalled());
  });

  it("explains a denied permission instead of offering a useless button", async () => {
    pushSupport.mockReturnValue("denied");
    renderToggle();

    await waitFor(() =>
      expect(screen.getByText(/bloqueaste|you blocked/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /activar|turn on/i })).not.toBeInTheDocument();
  });

  it("says a browser cannot do this, without blaming the deployment", async () => {
    pushSupport.mockReturnValue("unsupported");
    renderToggle();

    await waitFor(() =>
      expect(screen.getByText(/este navegador|this browser/i)).toBeInTheDocument(),
    );
  });

  it("says the deployment has no keys, without blaming the browser", async () => {
    pushKey.mockResolvedValue({ enabled: false, public_key: null });
    renderToggle();

    await waitFor(() =>
      expect(screen.getByText(/VAPID_PUBLIC_KEY/)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /activar|turn on/i })).not.toBeInTheDocument();
  });

  it("reports a failure rather than looking like it worked", async () => {
    enablePush.mockResolvedValue({ ok: false, permission: "default", reason: "not_configured" });
    renderToggle();
    await waitFor(() => enableButton());

    fireEvent.click(enableButton());

    await waitFor(() =>
      expect(screen.getByText(/no se pudieron|could not turn/i)).toBeInTheDocument(),
    );
  });

  it("lists the devices already registered", async () => {
    pushSupport.mockReturnValue("granted");
    pushDevices.mockResolvedValue({
      items: [
        {
          id: "S1",
          endpoint_hint: "abcdef123456",
          user_agent: "iPhone Safari",
          enabled: true,
          failure_count: 0,
          last_success_at: null,
          created_at: "2026-09-06T09:00:00",
        },
      ],
    });
    renderToggle();

    await waitFor(() => expect(screen.getByText("iPhone Safari")).toBeInTheDocument());
  });

  it("keeps an inactive device visible", async () => {
    pushSupport.mockReturnValue("granted");
    pushDevices.mockResolvedValue({
      items: [
        {
          id: "S2",
          endpoint_hint: "zzzzzz999999",
          user_agent: "Old Android",
          enabled: false,
          failure_count: 3,
          last_success_at: null,
          created_at: "2026-01-01T09:00:00",
        },
      ],
    });
    renderToggle();

    // So "why did my old phone stop working" has an answer.
    await waitFor(() => expect(screen.getByText(/inactivo|inactive/i)).toBeInTheDocument());
  });

  it("tells the user what a notification will and will not say", async () => {
    renderToggle();

    await waitFor(() =>
      expect(
        screen.getByText(/nunca contienen información del paciente|never contain patient/i),
      ).toBeInTheDocument(),
    );
  });
});
