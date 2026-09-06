/** The task inbox.
 *
 * The tests that carry weight here are the optimistic ones. Removing a row
 * before the server confirms is what makes an inbox feel responsive, and it is
 * also how a clinician ends up believing they closed something they did not —
 * so the rollback on failure matters more than the happy path.
 *
 * Note on the queries: `DataList` renders the card shape and the table shape
 * at every width and lets CSS choose (SPEC-017), so every row's text is in
 * the DOM twice. That is the design — one column set, two shapes, no way for
 * them to drift — and it means these tests ask for *all* matches rather than
 * a single one.
 *
 * Verifies AC-018-17, AC-018-18 (docs/specs/SPEC-018-unified-tasks.md).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TasksPage from "@/app/tasks/page";
import { ApiError, type ClinicalTask } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";
import { ToastProvider } from "@/components/ui/toast";

const searchParams = vi.fn(() => new URLSearchParams());
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams(),
  useRouter: () => ({ replace }),
}));

const listTasks = vi.fn();
const completeTask = vi.fn();
const dismissTask = vi.fn();
const claimTask = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listTasks: (...args: unknown[]) => listTasks(...args),
      completeTask: (...args: unknown[]) => completeTask(...args),
      dismissTask: (...args: unknown[]) => dismissTask(...args),
      claimTask: (...args: unknown[]) => claimTask(...args),
      reopenTask: vi.fn().mockResolvedValue({}),
      badges: vi.fn().mockResolvedValue({}),
    },
  };
});

function task(overrides: Partial<ClinicalTask> = {}): ClinicalTask {
  return {
    id: "T1",
    source: { kind: "alert", id: "A1" },
    category: "alert",
    severity: "high",
    status: "open",
    title: "Potasio crítico",
    detail: "",
    context: {},
    patient_id: "P1",
    patient_name: "Ana Ruiz",
    assigned_to_user_id: null,
    due_at: null,
    snoozed_until: null,
    escalation_level: 0,
    dismiss_reason: "",
    closed_at: null,
    created_at: "2026-09-06T12:00:00",
    completable: true,
    completable_refusal: "",
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ToastProvider>
          <TasksPage />
        </ToastProvider>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe("TasksPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParams.mockReturnValue(new URLSearchParams());
    listTasks.mockResolvedValue({
      items: [task(), task({ id: "T2", title: "Revisar receta", severity: "low" })],
      total_count: 2,
      limit: 50,
      offset: 0,
      has_more: false,
    });
  });

  it("lists the open inbox with its patient names", async () => {
    renderPage();

    expect((await screen.findAllByText("Potasio crítico")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ana Ruiz").length).toBeGreaterThan(0);
  });

  it("AC-018-17 — removes a resolved row immediately, before the server answers", async () => {
    let resolveRequest: (value: unknown) => void = () => {};
    completeTask.mockReturnValue(new Promise((res) => (resolveRequest = res)));
    renderPage();
    await screen.findAllByText("Potasio crítico");

    fireEvent.click(screen.getAllByRole("button", { name: /task actions/i })[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: /mark done/i }));

    // The row is gone while the request is still in flight — that is the point.
    await waitFor(() => expect(screen.queryAllByText("Potasio crítico")).toHaveLength(0));
    resolveRequest({});
  });

  it("AC-018-18 — puts the row back and explains when the server refuses", async () => {
    completeTask.mockRejectedValue(new ApiError(409, "already resolved elsewhere"));
    renderPage();
    await screen.findAllByText("Potasio crítico");

    fireEvent.click(screen.getAllByRole("button", { name: /task actions/i })[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: /mark done/i }));

    // A silent failure would leave a clinician sure they had handled it.
    expect(await screen.findByText("already resolved elsewhere")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Potasio crítico").length).toBeGreaterThan(0));
  });

  it("offers an undo after a row leaves the list", async () => {
    completeTask.mockResolvedValue(task({ status: "done" }));
    renderPage();
    await screen.findAllByText("Potasio crítico");

    fireEvent.click(screen.getAllByRole("button", { name: /task actions/i })[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: /mark done/i }));

    expect(await screen.findByRole("button", { name: /undo/i })).toBeInTheDocument();
  });

  it("does not offer to complete a task whose source refuses it", async () => {
    listTasks.mockResolvedValue({
      items: [
        task({
          id: "T3",
          category: "approval",
          source: { kind: "approval", id: "PA1" },
          title: "Aprobar mensaje",
          completable: false,
          completable_refusal: "approve or reject the message itself",
        }),
      ],
      total_count: 1,
      limit: 50,
      offset: 0,
      has_more: false,
    });
    renderPage();
    await screen.findAllByText("Aprobar mensaje");

    fireEvent.click(screen.getAllByRole("button", { name: /task actions/i })[0]);

    // Better to omit the button than to let someone press it and get a 409.
    expect(screen.queryByRole("menuitem", { name: /mark done/i })).toBeNull();
  });

  it("never offers to snooze a critical task", async () => {
    listTasks.mockResolvedValue({
      items: [task({ severity: "critical" })],
      total_count: 1,
      limit: 50,
      offset: 0,
      has_more: false,
    });
    renderPage();
    await screen.findAllByText("Potasio crítico");

    fireEvent.click(screen.getAllByRole("button", { name: /task actions/i })[0]);

    expect(screen.queryByRole("menuitem", { name: /snooze/i })).toBeNull();
  });

  it("requires a reason before dismissing", async () => {
    renderPage();
    await screen.findAllByText("Potasio crítico");

    fireEvent.click(screen.getAllByRole("button", { name: /task actions/i })[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: /dismiss/i }));

    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: /dismiss/i });
    expect(confirm).toBeDisabled();

    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "duplicada" } });
    expect(confirm).toBeEnabled();
  });

  it("drives the query from the URL, so a filtered inbox is a link", async () => {
    searchParams.mockReturnValue(new URLSearchParams("scope=mine&overdue=1"));
    renderPage();

    await waitFor(() => expect(listTasks).toHaveBeenCalled());
    expect(listTasks).toHaveBeenCalledWith(
      expect.objectContaining({ assignee: "me", overdue: true }),
    );
  });

  it("shows a retry when the inbox cannot be loaded", async () => {
    listTasks.mockRejectedValue(new ApiError(500, "boom"));
    renderPage();

    expect(await screen.findByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
