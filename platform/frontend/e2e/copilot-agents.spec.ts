import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** The copilot names agents by what they do, not by id. The stream below stands
 * in for /api/agents/consult/stream; the ids are the ones the backend sends. */
const sse = (events: unknown[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");

const STREAM = sse([
  { event: "routing", agents: ["drug_safety"] },
  { event: "agent_completed", agent: "drug_safety", tool_calls: [] },
  {
    event: "final",
    answer: "Avoid combining warfarin with ibuprofen.",
    agents_involved: ["drug-safety", "coordinator"],
    tool_calls: [],
    citation_report: { verified: [], fabricated: [], total_checked: 0 },
    verification_report: { claims: [], contradictions: [] },
    abstention: { status: "answer", reason: null, confidence: 1, supported_claim_ratio: 1, message: "" },
    explanation: {
      steps: [{ agent: "drug-safety", action: "Checked interactions", tool: "check_drug_interactions" }],
    },
    trace: { llm_calls: [] },
  },
  { event: "persisted", id: "c-1" },
]);

test.describe("agents in the copilot", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.route("**/api/agents/consult/stream", (r) =>
      r.fulfill({ status: 200, contentType: "text/event-stream", body: STREAM }),
    );
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Open Copilot Chat" }).click();
    await page.getByPlaceholder("Ask a clinical question…").fill("warfarin and ibuprofen?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("Avoid combining warfarin with ibuprofen.")).toBeVisible();
  });

  test("shows what each agent does, never its id", async ({ page }) => {
    await expect(page.getByText("Medication Interactions").first()).toBeVisible();
    await expect(page.getByText("drug-safety", { exact: true })).toHaveCount(0);
    await expect(page.getByText("drug_safety", { exact: true })).toHaveCount(0);
  });

  test("an agent this build does not know is shown as it came", async ({ page }) => {
    await expect(page.getByText("coordinator", { exact: true })).toBeVisible();
  });
});
