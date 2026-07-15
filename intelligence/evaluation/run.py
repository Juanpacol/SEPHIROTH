"""CLI entry point for the RAG evaluation harness.

    python -m intelligence.evaluation.run --mode ci
    python -m intelligence.evaluation.run --mode full --record [--skip-pubmed] [--model NAME]

`--mode ci` is fully offline and deterministic — this is what CI runs on
every PR. `--mode full` talks to a locally running Ollama server and is
meant to be run by hand (or via the `/eval` skill) to refresh the
committed baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone

from intelligence.evaluation import runner


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


def _print_table(rows) -> None:
    lines = ["| Metric | Value | Threshold | Status |", "|---|---|---|---|"]
    for row in rows:
        value = "n/a" if row["value"] is None else f"{row['value']:.4f}"
        status = "PASS" if row["passed"] else "FAIL"
        lines.append(f"| {row['metric']} | {value} | {row['threshold']:.4f} | {status} |")
    table = "\n".join(lines)
    print(table)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write("## RAG Evaluation\n\n" + table + "\n")


def _run_ci() -> int:
    result = runner.run_ci_mode()
    print(f"Cases evaluated: {result['n_cases']}")
    if result["stale_results"]:
        print(
            "WARNING: results/latest.json is missing or stale relative to "
            "datasets/golden.json / transcripts/ — regenerate with "
            "`--mode full --record` before merging.",
            file=sys.stderr,
        )
    _print_table(result["threshold_rows"])
    print(f"\nOverall: {'PASS' if result['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


def _run_full(record: bool, skip_pubmed: bool, model: str) -> int:
    from core.config import settings  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime
    from intelligence.llm.ollama_client import OllamaClient

    async def _main() -> int:
        client = OllamaClient(host=settings.ollama_host, model=model)
        results = await runner.run_full_mode(
            client,
            record=record,
            skip_pubmed=skip_pubmed,
            git_sha=_git_sha(),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        print(f"Model: {results['run']['model']}")
        print(f"Retrieval: {results['retrieval']}")
        print(f"Citation: {results['citation']}")
        print(f"Faithfulness: {results['faithfulness']}")
        if record:
            print(f"\nWrote {runner.RESULTS_PATH} and transcripts to {runner.TRANSCRIPTS_DIR}")
        return 0

    return asyncio.run(_main())


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG evaluation harness")
    parser.add_argument("--mode", choices=["ci", "full"], required=True)
    parser.add_argument("--record", action="store_true", help="full mode: overwrite transcripts + results")
    parser.add_argument(
        "--skip-pubmed",
        action="store_true",
        help="full mode: disable search_pubmed for reproducibility",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="full mode: Ollama model override (defaults to settings.ollama_model)",
    )
    args = parser.parse_args()

    if args.mode == "ci":
        return _run_ci()

    from core.config import settings  # noqa: PLC0415 — platform/ is on PYTHONPATH at runtime

    return _run_full(args.record, args.skip_pubmed, args.model or settings.ollama_model)


if __name__ == "__main__":
    raise SystemExit(main())
