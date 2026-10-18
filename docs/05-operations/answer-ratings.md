# Answer ratings and the review queue (AB#16)

A clinician rates an answer in the copilot, and the ones rated "not useful" wait in a queue until someone closes them. A human signal, separate from the automatic verification: a rating never changes the answer or its status.

## Rating

Under each persisted answer: **Useful** (saves on the click) or **Not useful** (asks for a reason, `incorrect` / `incomplete` / `unsafe` / `no_sources` / `other`, and an optional comment of up to 500 characters, then saves).

`POST /api/agents/consultations/{id}/rating` with `{value, reason?, comment?}`. Only the clinician who owns the consultation can rate it; anyone else gets 404. One rating per consultation and user: rating again replaces it. `GET /api/agents/history` returns the caller's rating on each item.

`comment` is clinical text and is encrypted at rest like the other PHI columns (`ADR-014`). The form tells the user not to type patient identifiers.

## Queue

Clinician-only, under `/api/quality`:

| Route | Does |
|---|---|
| `GET /queue?status=pending\|reviewed\|all` | "Not useful" ratings, oldest first: reason, comment, provider, model, fallback, review state. No question or answer text; open the consultation by `consultation_id`. |
| `POST /queue/{rating_id}/review` | Close an item: `outcome` is `model_failure`, `source_failure`, `false_alarm` or `no_action`, plus an optional note. Records who and when. A second review is a 409. |

Changing a rating to a different verdict reopens it as pending, since the earlier review judged a verdict that no longer stands. Sending the same verdict again changes nothing.

Without a user, the read-only review token (`docs/05-operations/review-endpoint.md`) reads the same queue at `GET /api/review/queue`, with the comment de-identified and no ids that identify a row.

## Dashboard

`GET /api/dashboard/ai` adds `ratings_count`, `helpful_count`, `helpful_ratio` (null with no ratings) and `pending_review_count`; the dashboard shows them as "Answer quality".

Not built: a page in the app to work the queue (the routes are there), and showing a past rating in the history views.
