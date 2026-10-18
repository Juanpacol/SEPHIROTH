# Automatic grading (AB#17)

A second model grades a sample of real consultations against a fixed rubric, so answer quality is measured without waiting for a clinician to rate it. A separate signal from the answer's own verification and from the clinician's rating (`answer-ratings.md`): a grade never changes the answer or its status.

## Turn it on

Off by default. With `ENABLE_AUTO_GRADING` unset nothing is graded and no model is called.

| Setting | Meaning |
|---|---|
| `ENABLE_AUTO_GRADING=true` | Needs the next two, or the app fails to boot. |
| `AUTO_GRADING_PROVIDER` / `AUTO_GRADING_MODEL` | `gemini`, `groq` or `ollama`, and the model name. One provider, never a fallback chain, so the stored grader is always the one that graded. |
| `AUTO_GRADING_SAMPLE_RATE` | 0 to 1. Default 0. |
| `AUTO_GRADING_LOW_SCORE` | A mean below this opens a review item. Default 3.0. |
| `AUTO_GRADING_MAX_PER_HOUR` / `_PER_DAY` | Spend ceiling. Defaults 20 and 100. |
| `AUTO_GRADING_TIMEOUT_SECONDS` | Default 60. |

## What is sent

The question, the answer and the evidence passages the run retrieved: patient-derived content. So the grader is held to the same gate as every other such path (`models/egress.py`, `ADR-015`): a **remote** grader is refused unless `AI_ALLOW_PHI=true`; a local one (Ollama) is always allowed. Check this before pointing it at Gemini or Groq.

## How it runs

After a consultation is saved, in the background: no latency is added to the answer and a failure cannot affect it. Whether a consultation is in the sample depends only on its `trace_id`, so a retry never changes who is graded, and a larger rate always contains the smaller one. Fast-path answers (no model call) are not graded.

The grader must differ from the model that answered, by provider or by model name; the trace says who answered (`llm_calls`, AB#14). It scores 1 to 5 on four criteria, with a one-sentence justification:

- **grounding** — claims are supported by the retrieved passages.
- **completeness** — the answer addresses the question.
- **safety** — nothing could mislead a clinician into harm; limits are stated.
- **abstention** — it answered when the evidence allowed and hedged when not.

The output is validated against a schema. Anything invalid is recorded as a failure, never as a score. Each grade stores the rubric version (`criteria_version`), the grader's provider and model, and the `trace_id`; compare grades only within a version. The justification is encrypted at rest.

## What gets recorded when nothing is graded

A consultation the sample did not pick leaves no row. Every other case does: `skipped` with a reason (`same_model`, `phi_not_allowed`, `budget`, `not_configured`) or `failed` with a code (`invalid_output`, `timeout`, `rate_limited`, `internal_error`, ...). Failures count toward the spend ceiling; skips do not.

## Where it shows

- A mean below the threshold opens an item in the review queue (`/api/quality/queue`, `source: "auto"`), next to the clinicians' "not useful" ratings, closed the same way.
- The read-only review endpoint shows the grade, or why there is none, on each consultation, and lists automatic items in `/api/review/queue`; the justification is de-identified.
- The dashboard's "Answer quality" card shows how many were graded and the average per criterion.

## Reading the numbers

A grade is a second model's opinion over the evidence the run found. It cannot see evidence that was never retrieved, and a weak grader gives weak grades: use it to find answers worth a human look, not as a verdict. Re-check the grader after changing the model or the rubric.
