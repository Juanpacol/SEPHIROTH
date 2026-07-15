---
name: eval
description: Run the RAG evaluation harness and report metric deltas — use after touching data/rag, the Evidence Agent, or Citation Guard, or whenever the user asks to check/update the eval numbers.
---

# /eval — run the RAG evaluation harness

Two modes; pick based on whether Ollama is available and whether the user asked for a quick check or a full refresh.

## 1. Quick check (`--mode ci`, always safe, no Ollama needed)

```bash
cd clinical-ai-copilot
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
```

Read the printed table. If it says `Overall: FAIL`, report which metric(s) dropped below threshold and by how much — check `git diff` on `data/rag/__init__.py`, `intelligence/agents/citation_guard.py`, or `intelligence/agents/__init__.py` (EvidenceAgent prompt) for what likely caused it.

If it warns `results/latest.json is missing or stale`, the dataset or transcripts changed since the last full run — offer to run `--mode full --record` (below) if Ollama is reachable, or tell the user it needs a local refresh before merging.

## 2. Full refresh (`--mode full --record`, needs local Ollama)

Check Ollama is up first:
```bash
curl -s -m 3 "${OLLAMA_HOST:-http://127.0.0.1:11435}/api/tags" > /dev/null && echo reachable
```

If reachable, run the real Evidence Agent against every golden case and refresh the committed baseline:
```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode full --record --skip-pubmed
```
(`--skip-pubmed` keeps transcripts reproducible — PubMed responses vary run to run.)

Omit `--skip-pubmed` only if the user explicitly wants live PubMed citations exercised too.

Add `--model <name>` to override the model (defaults to `settings.ollama_model`, i.e. `qwen3:8b`). Useful if the production model isn't pulled locally yet — check `intelligence/evaluation/results/latest.json`'s `run.model` field to see what the committed baseline was actually generated with, and flag it in your summary if it's a stand-in rather than the production model.

## After a full refresh

1. Diff the printed Retrieval / Citation / Faithfulness numbers against the previous `results/latest.json` (`git diff intelligence/evaluation/results/latest.json` before staging) and summarize what moved and why.
2. Update the metric table in `README.md`'s `## Evaluation` section to match the new numbers exactly — a stale README table is worse than no table.
3. Remind the user: `results/latest.json` and `intelligence/evaluation/transcripts/*.json` must be committed together (they're hash-linked — CI checks the pair for staleness). `git add intelligence/evaluation/`.
