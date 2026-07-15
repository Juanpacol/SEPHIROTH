---
name: release-check
description: Run the full local gate (lint, tests+coverage, eval regression check, README/baseline consistency, clean tree) before pushing — use before opening a PR or when the user asks "is this ready to push?".
---

# /release-check — the same gate CI runs, run locally first

Run each step in order and stop at the first failure — report exactly which check failed and why, don't silently continue past a red step.

```bash
cd clinical-ai-copilot
```

## 1. Lint

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

If `ruff format --check` fails, that's auto-fixable: `.venv/bin/ruff format .` then re-review the diff before continuing (formatting changes should be whitespace/quote-only — if anything looks semantically different, stop and investigate).

## 2. Tests + coverage gate

```bash
PYTHONPATH=.:platform .venv/bin/pytest --cov
```

Must show `Required test coverage of 87.0% reached` and all tests passing. A coverage drop below 87% blocks — don't lower the threshold in `pyproject.toml` to make it pass; add tests for the uncovered lines instead (`--cov-report=term-missing` will show exactly which lines).

## 3. Eval regression gate (offline)

```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
```

Must print `Overall: PASS` with no staleness warning. If it warns the baseline is stale, `data/rag/SEED_GUIDELINES` or `intelligence/evaluation/datasets/golden.json` changed without a matching `--mode full --record` run — use the `/eval` skill to refresh before continuing.

## 4. README ↔ baseline consistency

Compare the metric table in `README.md`'s `## Evaluation` section against `intelligence/evaluation/results/latest.json`. If any number differs, the README wasn't updated after the last eval refresh — fix it now (this is a quick, common miss).

## 5. Clean tree check

```bash
git status --short
```

Everything intended for this change should be staged/committed; nothing stray (stray `__pycache__`, `.next/`, or other build artifacts should already be gitignored — if you see any tracked, that's a regression in `.gitignore` coverage worth flagging).

## Result

Green on all five means the branch is safe to push and open a PR. Summarize which steps passed; if anything failed, name the exact command and output that failed rather than a general "something's wrong."
