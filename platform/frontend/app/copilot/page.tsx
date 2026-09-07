import { redirect } from "next/navigation";

/** Copilot Chat moved from a dedicated page to a floating widget available
 * on every clinician page (see components/copilot/copilot-widget.tsx) —
 * this keeps old bookmarks/links to /copilot working instead of a 404. */
export default function CopilotRedirect() {
  redirect("/dashboard");
}
