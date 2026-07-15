---
name: add-guideline
description: Add a new clinical guideline document to the RAG corpus with matching golden/paraphrase eval cases and tests — use when the user wants to expand data/rag/SEED_GUIDELINES with a new topic.
---

# /add-guideline <topic> — extend the RAG corpus correctly

Adding a document to `data/rag/SEED_GUIDELINES` without updating the eval dataset silently degrades the evaluation harness (the new doc becomes an untested distractor, or worse, a topic no golden case ever exercises). Follow every step.

## 1. Add the document

In `data/rag/__init__.py`, append a `Document` to `SEED_GUIDELINES`:

```python
Document(
    id="<org>-<year>-<topic>",   # e.g. "acc-aha-2024-lipids" — must be globally unique
    content=(
        "Short, factual excerpt paraphrased from the public guideline — "
        "2-3 sentences, same terse style as neighboring entries."
    ),
    source="<Guideline Full Name>",
    metadata={"organization": "<Org>", "year": <year>, "title": "<Short Title>"},
),
```

Match the existing style: real public guidelines (ADA, USPSTF, KDIGO, ACC/AHA, GINA, IDSA, WHO, etc.), paraphrased not verbatim-copied, 2-3 sentences.

## 2. Add matching golden dataset cases

In `intelligence/evaluation/datasets/golden.json`, add:
- **One "golden" case**: a direct-phrasing question this new document should answer. Set `relevant_doc_ids: ["<the new doc id>"]` and `expected_citation_substrings` matching the document's `source` or `metadata.title`.
- **One "paraphrase" case** (recommended): a colloquial rephrasing of the same question — this is what stress-tests the keyword retriever and is the most informative addition.

Keep `id` fields kebab-case and descriptive (e.g. `"lipids-statin-intensity"`).

## 3. Verify locally

```bash
cd clinical-ai-copilot
PYTHONPATH=.:platform .venv/bin/pytest tests/test_rag_pipeline.py tests/test_evaluation.py -q
```

`test_evaluation.py::test_load_dataset_real_file_loads_without_error` will catch a typo'd `relevant_doc_ids` (it validates every id exists in the corpus) — if it fails, fix the id before continuing.

## 4. Regenerate the baseline

The dataset changed, so the committed `results/latest.json` is now stale relative to it — `--mode ci` will warn or fail until it's refreshed. Invoke the `/eval` skill with `--full` (or run directly):

```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode full --record --skip-pubmed
```

Then update the README's `## Evaluation` metric table to match, per the `/eval` skill's "after a full refresh" steps.

## 5. Consider a targeted test

If the new topic has a distinctive vocabulary that could confuse retrieval against neighboring corpus entries, add a case to `tests/test_rag_pipeline.py` asserting the new doc ranks first for its golden query — cheap insurance against future corpus growth silently degrading this one.
