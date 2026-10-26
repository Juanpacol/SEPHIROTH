/** `answer_delta` SSE handling in `CopilotPanel` (AB#67, token streaming).
 * `fetch("/api/agents/consult/stream")` is mocked with a hand-rolled
 * `ReadableStream`-shaped reader (`{ getReader: () => ({ read }) }`) that
 * yields one `data: {json}\n\n` frame per call — the exact shape
 * `submit()` consumes via `res.body.getReader()`. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CopilotPanel from "@/components/copilot/copilot-panel";
import { LanguageProvider } from "@/lib/language";

// jsdom has no layout engine and doesn't implement `scrollIntoView` — the
// composer's `onFocus` handler calls it (see copilot-panel.tsx's iOS
// keyboard comment), and a click anywhere in the composer (including on
// the Send button, via bubbling to the wrapping div's `onClick`) focuses
// the textarea.
Element.prototype.scrollIntoView = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    patients: vi.fn().mockResolvedValue([]),
    exportConsultation: vi.fn(),
  },
}));

function sseFrame(event: Record<string, unknown>): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/** A `fetch` mock whose response's `body.getReader()` yields one `frames[i]`
 * chunk per `read()` call, then signals `done`. */
function mockStreamResponse(frames: string[]) {
  const encoder = new TextEncoder();
  let i = 0;
  const reader = {
    read: async () => {
      if (i < frames.length) {
        const value = encoder.encode(frames[i]);
        i += 1;
        return { done: false, value };
      }
      return { done: true, value: undefined };
    },
  };
  return {
    ok: true,
    body: { getReader: () => reader },
  } as unknown as Response;
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <CopilotPanel />
      </LanguageProvider>
    </QueryClientProvider>
  );
}

async function submit(text: string) {
  const textarea = screen.getByPlaceholderText("Ask a clinical question…");
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.click(screen.getByLabelText("Send"));
}

describe("CopilotPanel answer_delta streaming", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("accumulates deltas into the visible answer text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockStreamResponse([
          sseFrame({ event: "routing", agents: ["evidence"] }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "Metformin ", reset: false }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "remains first-line.", reset: false }),
        ])
      )
    );

    renderPanel();
    await submit("first-line therapy?");

    await waitFor(() => {
      expect(screen.getByText(/Metformin remains first-line\./)).toBeInTheDocument();
    });
  });

  it("clears the streamed answer on a reset:true delta", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockStreamResponse([
          sseFrame({ event: "routing", agents: ["evidence"] }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "stale draft", reset: false }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "", reset: true }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "fresh answer", reset: false }),
        ])
      )
    );

    renderPanel();
    await submit("first-line therapy?");

    await waitFor(() => {
      expect(screen.getByText("fresh answer")).toBeInTheDocument();
    });
    expect(screen.queryByText(/stale draft/)).not.toBeInTheDocument();
  });

  it("shows only final.answer immediately when final follows deltas with a different answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockStreamResponse([
          sseFrame({ event: "routing", agents: ["evidence"] }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "provisional draft", reset: false }),
          sseFrame({
            event: "final",
            answer: "the verified final answer",
            agents_involved: ["evidence"],
            tool_calls: [],
            citation_report: { verified: [], fabricated: [], total_checked: 0 },
            explanation: { steps: [] },
            abstention: null,
            verification_report: { claims: [], contradictions: [] },
            trace: {},
          }),
        ])
      )
    );

    renderPanel();
    await submit("first-line therapy?");

    await waitFor(() => {
      expect(screen.getByText("the verified final answer")).toBeInTheDocument();
    });
    // No word-by-word reveal: the full final answer is visible right away,
    // not just a prefix of it.
    expect(screen.queryByText(/provisional draft/)).not.toBeInTheDocument();
  });

  it("still reveals the answer when final arrives with no prior deltas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockStreamResponse([
          sseFrame({ event: "routing", agents: ["evidence"] }),
          sseFrame({
            event: "final",
            answer: "revealed word by word",
            agents_involved: ["evidence"],
            tool_calls: [],
            citation_report: { verified: [], fabricated: [], total_checked: 0 },
            explanation: { steps: [] },
            abstention: null,
            verification_report: { claims: [], contradictions: [] },
            trace: {},
          }),
        ])
      )
    );

    renderPanel();
    await submit("first-line therapy?");

    await waitFor(
      () => {
        expect(screen.getByText("revealed word by word")).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it("leaves no streamed answer text after an error following deltas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockStreamResponse([
          sseFrame({ event: "routing", agents: ["evidence"] }),
          sseFrame({ event: "answer_delta", agent: "evidence", text: "partial text", reset: false }),
          sseFrame({ event: "error", detail: "the model is unavailable" }),
        ])
      )
    );

    renderPanel();
    await submit("first-line therapy?");

    await waitFor(() => {
      expect(screen.getByText("the model is unavailable")).toBeInTheDocument();
    });
    expect(screen.queryByText(/partial text/)).not.toBeInTheDocument();
  });
});
