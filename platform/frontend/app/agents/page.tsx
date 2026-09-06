import { redirect } from "next/navigation";

/** Agent activity is an operator's view of how the AI is behaving, not a
 * clinical destination — it moved under `/admin` (SPEC-019) so the primary
 * navigation only lists places a clinician goes to do clinical work. */
export default function AgentsRedirect() {
  redirect("/admin/ai");
}
