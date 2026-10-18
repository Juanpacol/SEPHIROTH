import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ExplainabilityPanel from "@/components/explainability-panel";
import { type Explanation, type LLMCall } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const EXPLANATION: Explanation = {
  steps: [{ agent: "evidence", action: "Searched clinical guidelines", tool: "search_clinical_guidelines" }],
  citations_verified: 2,
  citations_removed: 0,
};

const call = (over: Partial<LLMCall> = {}): LLMCall => ({
  kind: "chat",
  provider: "gemini",
  model: "gemini-flash-latest",
  ok: true,
  error: "",
  fallback: false,
  fallback_from: "",
  fallback_reason: "",
  duration_ms: 900,
  prompt_tokens: 0,
  completion_tokens: 0,
  ...over,
});

function renderPanel(props: { explanation?: Explanation; llmCalls?: LLMCall[]; traceId?: string } = {}) {
  render(
    <LanguageProvider>
      <ExplainabilityPanel explanation={props.explanation ?? EXPLANATION} {...props} />
    </LanguageProvider>,
  );
}

const open = () => fireEvent.click(screen.getByRole("button", { name: /How this answer was produced/ }));

describe("ExplainabilityPanel: which model answered", () => {
  it("keeps the models hidden until the panel is opened", () => {
    renderPanel({ llmCalls: [call()], traceId: "abc123" });

    expect(screen.queryByText("Models used")).not.toBeInTheDocument();
    open();
    expect(screen.getByText("Models used")).toBeInTheDocument();
  });

  it("names the provider and model that answered", () => {
    renderPanel({ llmCalls: [call()] });
    open();

    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.getByText("Gemini · gemini-flash-latest")).toBeInTheDocument();
    expect(screen.queryByText("fallback")).not.toBeInTheDocument();
  });

  it("shows the failed primary and the fallback that answered instead", () => {
    renderPanel({
      llmCalls: [
        call({ ok: false, error: "rate_limited" }),
        call({
          provider: "groq",
          model: "llama-3.3-70b-versatile",
          fallback: true,
          fallback_from: "gemini",
          fallback_reason: "rate_limited",
        }),
      ],
    });
    open();

    const rows = screen.getAllByRole("listitem").filter((li) => li.textContent?.includes(" · "));
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("failed: rate limit reached")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Groq · llama-3.3-70b-versatile")).toBeInTheDocument();
    expect(within(rows[1]).getByText("fallback")).toBeInTheDocument();
  });

  it("labels the different kinds of call", () => {
    renderPanel({
      llmCalls: [call(), call({ kind: "generate_json" }), call({ kind: "describe_image_stream" })],
    });
    open();

    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.getByText("Check or routing")).toBeInTheDocument();
    expect(screen.getByText("Image analysis")).toBeInTheDocument();
  });

  it("shows a reason code it does not know as it is, without a translation error", () => {
    renderPanel({ llmCalls: [call({ ok: false, error: "brand_new_reason" })] });
    open();

    expect(screen.getByText("failed: brand_new_reason")).toBeInTheDocument();
  });

  it("shows the trace id so a response can be found in the logs", () => {
    renderPanel({ llmCalls: [call()], traceId: "4f3a9c0de1b24c58a7d61e0b9f2c3a10" });
    open();

    expect(screen.getByText("4f3a9c0de1b24c58a7d61e0b9f2c3a10")).toBeInTheDocument();
    expect(screen.getByText(/Trace ID/)).toBeInTheDocument();
  });

  it("says no model was called when the list is empty but the answer has steps", () => {
    renderPanel({ llmCalls: [] });
    open();

    expect(screen.getByText("No model was called for this answer.")).toBeInTheDocument();
  });

  it("shows nothing about models when the trace is not known", () => {
    renderPanel({ llmCalls: undefined });
    open();

    expect(screen.queryByText("Models used")).not.toBeInTheDocument();
    expect(screen.getByText(/Searched clinical guidelines/)).toBeInTheDocument();
  });

  it("is still absent when there is nothing to explain, as before", () => {
    renderPanel({ explanation: { ...EXPLANATION, steps: [] }, llmCalls: [] });

    expect(screen.queryByRole("button", { name: /How this answer was produced/ })).not.toBeInTheDocument();
  });

  it("keeps the explanation steps exactly as they were", () => {
    renderPanel({ llmCalls: [call()] });
    open();

    expect(screen.getByText("evidence")).toBeInTheDocument();
    expect(screen.getByText(/Searched clinical guidelines/)).toBeInTheDocument();
  });
});
