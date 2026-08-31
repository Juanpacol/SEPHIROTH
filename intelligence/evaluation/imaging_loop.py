"""Self-improving loop over `imaging_eval.py`'s hallucination/consistency eval.

    PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.imaging_loop [--target 0.9] [--record]

Runs an ordered, hand-written list of prompt/config candidates against the
full imaging golden set (via `imaging_eval.run_case`/`_aggregate`, reused
as-is — no scoring logic is duplicated here), stops at the first candidate
whose `coherent_rate` clears `--target`, and prints a report of what to
change in `intelligence/mcp/vision_server.py` to apply it.

`coherent_rate` is the MINIMUM of the 5 rates `_aggregate` already computes
(modality_accuracy, anatomy_grounding, hallucination_free_rate,
no_diagnosis_rate, consistency_rate) — not a mean. A mean lets a perfect
score on 4 easy dimensions mask a bad score on the one that matters most
(measured: baseline's mean was a misleading 0.900 while
hallucination_free_rate alone was 0.500). A candidate is only as coherent
as its worst dimension.

This deliberately does NOT edit `vision_server.py`. A human applies the
winning candidate's prompt by hand after reading the report — see the plan
this script was built from (`docs/`-external, this session's plan mode
output) for the reasoning: auto-editing production prompts from an eval
loop with 4 golden cases is not a safe default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from intelligence.evaluation.imaging_eval import GOLDEN_PATH, _aggregate, _print_report, run_case

_RESULTS_PATH = Path(__file__).parent / "results" / "imaging_loop_latest.json"

NO_SPECULATION_SUFFIX = (
    " If no abnormality is visible, state that explicitly and do not speculate about possible findings."
)


@dataclass
class Candidate:
    name: str
    description: str
    # Returns an async callable(client, image_bytes, mime_type) -> (description, modality),
    # built from the candidate's prompt/option overrides. None = use imaging_eval's default.
    describe_fn: Optional[Callable] = None


def _make_describe_fn(prompt_suffix: str = ""):
    """Builds a `_describe_and_classify`-shaped callable with the given
    prompt override, without touching `vision_server.py` or any client's
    persistent config — the override lives only in this closure."""

    async def _describe(client, image_bytes: bytes, mime_type: str) -> tuple[str, str]:
        from intelligence.mcp.vision_server import DESCRIPTION_PROMPT, detect_modality

        prompt = DESCRIPTION_PROMPT + prompt_suffix
        description = await client.describe_image(image_bytes=image_bytes, mime_type=mime_type, prompt=prompt)
        modality = await detect_modality(image_bytes, mime_type)
        return description.strip(), modality

    return _describe


CANDIDATES = [
    Candidate(
        name="baseline",
        description="Current production DESCRIPTION_PROMPT, unchanged.",
        describe_fn=_make_describe_fn(),
    ),
    Candidate(
        name="no_speculation_prompt",
        description="Adds: 'If no abnormality is visible, state that explicitly and do not speculate.'",
        describe_fn=_make_describe_fn(prompt_suffix=NO_SPECULATION_SUFFIX),
    ),
]


def _coherent_rate(metrics: dict) -> float:
    """The WEAKEST of the 5 rates, not their average — a mean lets a
    perfect modality_accuracy/anatomy_grounding/consistency mask a bad
    hallucination_free_rate (measured: baseline scored a misleading 0.900
    average while hallucination_free_rate was only 0.500). A candidate is
    only as coherent as its worst dimension."""
    return min(metrics.values())


async def _run_candidate(client, golden: dict, candidate: Candidate) -> dict:
    import intelligence.evaluation.imaging_eval as imaging_eval

    original = imaging_eval._describe_and_classify
    imaging_eval._describe_and_classify = candidate.describe_fn
    try:
        results = []
        for case in golden["cases"]:
            result = await run_case(client, case)
            if result:
                results.append(result)
        summary = _aggregate(results)
    finally:
        imaging_eval._describe_and_classify = original

    return {"results": results, "summary": summary, "coherent_rate": _coherent_rate(summary["metrics"])}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target", type=float, default=0.9, help="Blended coherent_rate to stop at (default 0.9)"
    )
    parser.add_argument("--record", action="store_true", help="Write results/imaging_loop_latest.json")
    args = parser.parse_args()

    sys.path.insert(0, ".")
    sys.path.insert(0, "platform")
    from sephiroth.models import get_llm_client

    client = get_llm_client()
    golden = json.loads(GOLDEN_PATH.read_text())

    print(
        f"Running imaging self-improve loop, target coherent_rate >= {args.target:.2f}, "
        f"{len(CANDIDATES)} candidate(s), {len(golden['cases'])} golden case(s) each.\n"
    )

    outcomes = []
    winner = None
    for candidate in CANDIDATES:
        print(f"=== Candidate: {candidate.name} — {candidate.description} ===")
        outcome = await _run_candidate(client, golden, candidate)
        _print_report(outcome["results"], outcome["summary"])
        rate = outcome["coherent_rate"]
        print(f"\ncoherent_rate = {rate:.3f}  (target {args.target:.2f})\n")
        outcomes.append({"name": candidate.name, "coherent_rate": rate, "summary": outcome["summary"]})
        if rate >= args.target:
            winner = candidate
            break

    print("\n=== Loop summary ===")
    print("| Candidate | coherent_rate | Status |")
    print("|---|---|---|")
    for o in outcomes:
        status = (
            "WINNER"
            if winner and o["name"] == winner.name
            else ("PASS" if o["coherent_rate"] >= args.target else "below target")
        )
        print(f"| {o['name']} | {o['coherent_rate']:.3f} | {status} |")

    if winner and winner.name != "baseline":
        print(
            f"\nApply by hand: change DESCRIPTION_PROMPT in intelligence/mcp/vision_server.py "
            f"to the '{winner.name}' variant — {winner.description}\n"
            f"This script does NOT edit vision_server.py automatically."
        )
    elif winner and winner.name == "baseline":
        print("\nBaseline already clears the target — no prompt change needed.")
    else:
        print(
            f"\nNo candidate reached coherent_rate >= {args.target:.2f}. "
            "Consider adding another candidate (e.g. a lower-temperature variant, "
            "or a stronger vision model) rather than lowering the target."
        )

    if args.record:
        _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RESULTS_PATH.write_text(
            json.dumps(
                {
                    "target": args.target,
                    "winner": winner.name if winner else None,
                    "outcomes": [
                        {
                            "name": o["name"],
                            "coherent_rate": o["coherent_rate"],
                            "metrics": o["summary"]["metrics"],
                        }
                        for o in outcomes
                    ],
                },
                indent=2,
            )
        )
        print(f"\nWrote {_RESULTS_PATH}")

    return 0 if winner else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
